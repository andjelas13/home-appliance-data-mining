#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
podaci.py — Učitavanje podataka i priprema matrice obeležja (Zadaci 4, 5 i 6).

Opis:
Funkcija ucitaj_preciscene čita prečišćenu bazu u pandas tabelu i nju koriste
regresija, K-means i preporuke. Klasa Priprema od te tabele pravi numeričku
matricu obeležja za linearnu regresiju, a istu pripremu, snimljenu uz model,
koristi i aplikacija. Funkcija podeli deli redove na trening i test.
Gotove biblioteke za obučavanje se ne koriste; numpy i pandas služe samo za
rad sa nizovima i tabelama.

Koraci pripreme (klasa Priprema):

    1. Nedostajuće vrednosti — frižider bez upisane visine, televizor bez težine.
       Prazno polje popunjavam medijanom svoje kategorije, jer prosečna zapremina
       frižidera nema smisla za šporet. Ako kategorija nema nijednu vrednost te
       kolone (npr. kapacitet pranja kod televizora), uzimam medijanu svih
       proizvoda. Uz svaku kolonu ide i pokazatelj `_nedostaje` (0/1), da model
       zna da je vrednost popunjena.

    2. One-hot kodiranje — kategorija, brend i energetska skala postaju kolone
       0/1. Napisala sam ga ručno (bez get_dummies), da isti postupak radi i nad
       jednim proizvodom koji korisnik unese u formi.

    3. Standardizacija — svaka numerička kolona se svodi na sredinu 0 i
       standardnu devijaciju 1. Zapremina je u stotinama litara, a energetski
       rang u jedinicama, pa bez toga ista stopa učenja ne bi odgovarala svim
       kolonama i spust ne bi radio. Sredine i odstupanja se pamte.

    4. Članovi interakcije — standardizovana karakteristika × pokazivač
       kategorije, da npr. zapremina ima poseban koeficijent za svaku kategoriju.

Ulazi:
    šema preciscena, tabela proizvodi

Izlazi:
    nema fajlova; pokrenut kao skripta ispisuje veličinu matrice obeležja

Primer upotrebe:
    from podaci import ucitaj_preciscene, Priprema

    tabela = ucitaj_preciscene()
    priprema = Priprema(numericke=[...], kategoricke=["kategorija", "brend"])
    X, nazivi = priprema.nauci_i_primeni(tabela)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# dodajem folder kod u putanju, da bih uvezla paket zajednicko
sys.path.append(str(Path(__file__).resolve().parents[1]))
from zajednicko.baza import veza

# -------------------------------
# Podrazumevana obeležja
# -------------------------------
# numeričke karakteristike koje ulaze u matricu obeležja; izabrala sam one koje imaju jasno
# fizičko značenje i koje ima dovoljan broj proizvoda bar u jednoj kategoriji. Izuzetak je
# broj_programa, koji sam dodala zbog sušilica, iako ga ima samo deo njih.
NUMERICKE = [
    "dijagonala_inch",
    "zapremina_l",
    "zapremina_frizider_l",
    "zapremina_zamrzivac_l",
    "kapacitet_pranja_kg",
    "kapacitet_kompleta",
    "brzina_centrifuge",
    "snaga_w",
    "kapacitet_hladjenja_kw",
    "visina_cm",
    "sirina_cm",
    "dubina_cm",
    "tezina_kg",
    "nivo_buke_db",
    "broj_programa",
    "gabarit_cm3",
    "energetska_rang",          # rang klase unutar svoje skale (1 = najbolja)
]

# ove kategoričke kolone pretvaram u one-hot kolone
KATEGORICKE = ["kategorija", "brend", "energetska_skala"]

# brendove sa manje od 15 proizvoda stavljam u „ostalo", da model ne dobije stotine
# kolona koje su jedinica kod jednog ili dva proizvoda
NAJMANJE_PO_BRENDU = 15


# -------------------------------
# Učitavanje
# -------------------------------
def ucitaj_preciscene() -> pd.DataFrame:
    """
    Funkcija čita tabelu preciscena.proizvodi u pandas tabelu, samo proizvode koji
    imaju cenu, pretvara brojeve iz Decimal u float, dodaje kolonu energetska_rang
    i popunjava prazan brend i skalu.
    """
    # svi modeli predviđaju ili prikazuju cenu, pa proizvod bez cene ne učitavam
    with veza("preciscena") as konekcija:
        with konekcija.cursor() as kurzor:
            kurzor.execute("SELECT * FROM preciscena.proizvodi WHERE cena_min IS NOT NULL")
            # nazive kolona uzimam iz opisa rezultata upita, pa od svih redova pravim DataFrame
            kolone = [opis[0] for opis in kurzor.description]
            tabela = pd.DataFrame(kurzor.fetchall(), columns=kolone)

    # psycopg2 mi vraća NUMERIC kao Decimal, pa kolone tipa object pokušavam da
    # pretvorim u brojeve; kolone koje su već brojevi preskačem, a tekstualne
    # ne prođu pretvaranje i ostaju iste
    for kolona in tabela.columns:
        if tabela[kolona].dtype == object:
            uzorak = tabela[kolona].dropna()
            if len(uzorak) and not isinstance(uzorak.iloc[0], (int, float)):
                try:
                    tabela[kolona] = pd.to_numeric(tabela[kolona])
                except (ValueError, TypeError):
                    pass

    # staru i novu energetsku skalu ne spajam: rang je računat unutar svoje
    # skale (1 = najbolja), a oznaku skale puštam u model kao posebnu one-hot kolonu.
    # Praznu skalu popunjavam sa „nepoznata", a prazan brend sa „nepoznat"; fillna je isti
    # kao na vežbama, samo tamo tekst dobija najčešću vrednost (mode)
    tabela["energetska_rang"] = pd.to_numeric(tabela["energetska_klasa_num"], errors="coerce")
    tabela["energetska_skala"] = tabela["energetska_skala"].fillna("nepoznata")
    tabela["brend"] = tabela["brend"].fillna("nepoznat")

    print(f"[INFO] Učitano {len(tabela):,} proizvoda iz prečišćene baze".replace(",", "."))
    return tabela


# -------------------------------
# Priprema obeležja
# -------------------------------
class Priprema:
    """
    Klasa pretvara tabelu proizvoda u numeričku matricu obeležja.

    nauci_i_primeni() na skupu za treniranje pamti medijane po kategorijama,
    vrednosti za one-hot i parametre standardizacije. primeni() te iste
    parametre, bez ponovnog učenja, koristi za test skup i za proizvod iz forme,
    pa podaci iz testa ne cure u učenje.
    """

    def __init__(self, numericke: list[str] | None = None,
                 kategoricke: list[str] | None = None,
                 najmanje_po_brendu: int = NAJMANJE_PO_BRENDU,
                 interakcije: bool = True):
        """Pamti koje kolone ulaze u matricu i pravi prazna mesta za naučene parametre."""
        # ako kolone nisu zadate, uzimam podrazumevane NUMERICKE i KATEGORICKE; list() pravi kopiju
        self.numericke = list(numericke if numericke is not None else NUMERICKE)
        self.kategoricke = list(kategoricke if kategoricke is not None else KATEGORICKE)
        self.najmanje_po_brendu = najmanje_po_brendu
        self.interakcije = interakcije

        # naučene parametre popunjavam u nauci_i_primeni() ili ih učitavam iz JSON-a
        self.medijane_po_kategoriji: dict[str, dict[str, float]] = {}
        self.opste_medijane: dict[str, float] = {}
        self.vrednosti_kategorickih: dict[str, list[str]] = {}
        self.nazivi_kolona: list[str] = []
        self.sredine: np.ndarray | None = None
        self.odstupanja: np.ndarray | None = None

    # ---------------------------
    def nauci_i_primeni(self, tabela: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
        """
        Uči medijane, one-hot vrednosti i parametre standardizacije na datoj
        tabeli (skupu za treniranje) i vraća matricu obeležja i nazive kolona.
        """
        # prvo učim medijane i one-hot vrednosti, pa tek onda tim medijanama popunjavam numeričke kolone
        self._nauci_medijane(tabela)
        self._nauci_kategoricke(tabela)

        sirove_numericke, nazivi_numerickih = self._numericke_kolone(tabela)

        # sredinu i standardnu devijaciju računam samo za numeričke kolone, i to
        # posle popune praznih polja; pokazatelji i one-hot kolone su već 0/1
        self.sredine = sirove_numericke.mean(axis=0)
        self.odstupanja = sirove_numericke.std(axis=0)
        # kolona sa istom vrednošću u svim redovima ima std 0, pa joj stavljam 1 da ne delim nulom
        self.odstupanja[self.odstupanja == 0] = 1.0

        # nazive kolona pamtim u objektu, da se snime uz model
        matrica, nazivi = self._sastavi(tabela, sirove_numericke, nazivi_numerickih)
        self.nazivi_kolona = nazivi
        return matrica, nazivi

    def primeni(self, tabela: pd.DataFrame) -> np.ndarray:
        """Primenjuje već naučenu pripremu na nove podatke (test ili proizvod iz forme) i vraća matricu."""
        # bez naučenih sredina ne mogu da standardizujem, pa odmah prijavljujem grešku
        if self.sredine is None:
            raise RuntimeError("Priprema još nije naučena — pozovi nauci_i_primeni().")
        # ovde ništa ne učim, samo popunjavam i sastavljam matricu sa već zapamćenim parametrima
        sirove_numericke, nazivi_numerickih = self._numericke_kolone(tabela)
        matrica, _ = self._sastavi(tabela, sirove_numericke, nazivi_numerickih)
        return matrica

    # ---------------------------
    def _nauci_medijane(self, tabela: pd.DataFrame) -> None:
        """
        Za svaku numeričku kolonu računa opštu medijanu i medijanu po kategoriji
        i pamti ih za popunu praznih polja.
        """
        for kolona in self.numericke:
            if kolona not in tabela.columns:
                continue
            # vrednost koja nije broj errors="coerce" pretvara u NaN, pa je računam kao prazno polje
            vrednosti = pd.to_numeric(tabela[kolona], errors="coerce")
            # median() mi preskače prazna polja; ako je cela kolona prazna, opšta medijana je 0
            self.opste_medijane[kolona] = float(vrednosti.median()) if vrednosti.notna().any() else 0.0

            # kroz kategorije prolazim preko groupby; kategorija bez ijedne
            # vrednosti ne dobija medijanu, pa joj kasnije ide opšta
            po_kategoriji = {}
            for kategorija, deo in vrednosti.groupby(tabela["kategorija"]):
                if deo.notna().any():
                    po_kategoriji[kategorija] = float(deo.median())
            self.medijane_po_kategoriji[kolona] = po_kategoriji

    def _nauci_kategoricke(self, tabela: pd.DataFrame) -> None:
        """
        Pamti koje vrednosti kategoričkih kolona dobijaju svoju one-hot kolonu.
        Kod brenda zadržava samo brendove sa bar najmanje_po_brendu proizvoda i
        dodaje „ostalo"; kod ostalih kolona zadržava sve vrednosti.
        """
        for kolona in self.kategoricke:
            if kolona not in tabela.columns:
                continue
            # posle prebrojavanja sa value_counts brend filtriram pragom, a ostale kolone zadržavam cele, sortirane
            broj_pojavljivanja = tabela[kolona].value_counts()
            if kolona == "brend":
                zadrzane = broj_pojavljivanja[broj_pojavljivanja >= self.najmanje_po_brendu].index
                self.vrednosti_kategorickih[kolona] = sorted(zadrzane) + ["ostalo"]
            else:
                self.vrednosti_kategorickih[kolona] = sorted(broj_pojavljivanja.index)

    # ---------------------------
    def _numericke_kolone(self, tabela: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
        """
        Vraća matricu sirovih (nestandardizovanih) numeričkih kolona i njihove
        nazive. Prazno polje popunjava medijanom svoje kategorije, a ako ni ona
        ne postoji, opštom medijanom.
        """
        kolone, nazivi = [], []
        for kolona in self.numericke:
            if kolona not in tabela.columns:
                continue
            vrednosti = pd.to_numeric(tabela[kolona], errors="coerce")
            # za kolonu uzimam zapamćene medijane po kategoriji i opštu medijanu kao rezervu
            medijane = self.medijane_po_kategoriji.get(kolona, {})
            opsta = self.opste_medijane.get(kolona, 0.0)
            # map daje svakom redu medijanu njegove kategorije, a drugi fillna
            # popunjava ono što je i posle toga ostalo prazno. Ovo mi je kao fillna(mean())
            # sa vežbi, samo uzimam medijanu, jer na nju ne utiče nekoliko uređaja sa ogromnim vrednostima.
            popunjeno = vrednosti.fillna(tabela["kategorija"].map(medijane)).fillna(opsta)
            kolone.append(popunjeno.to_numpy(dtype=float))
            nazivi.append(kolona)
        # column_stack mi slaže kolone jednu pored druge u matricu
        return np.column_stack(kolone), nazivi

    def _sastavi(self, tabela: pd.DataFrame, sirove_numericke: np.ndarray,
                 nazivi_numerickih: list[str]) -> tuple[np.ndarray, list[str]]:
        """
        Sastavlja konačnu matricu redom: standardizovane numeričke kolone,
        pokazatelji nedostajanja, one-hot kolone i članovi interakcije.
        Vraća matricu i nazive svih kolona.
        """
        # standardizacija z = (x − sredina) / odstupanje, sa parametrima sa treninga;
        # na vežbama je to radio MinMaxScaler i svodio kolone na 0–1, a ja pravim z-vrednost
        standardizovane = (sirove_numericke - self.sredine) / self.odstupanja

        # delove matrice skupljam u listu, a nazive kolona dodajem istim redom
        delovi = [standardizovane]
        nazivi = list(nazivi_numerickih)

        # --- pokazatelji nedostajanja (0/1) ---
        # pokazatelj mi je 1 ako je polje bilo prazno u tabeli, pre popune medijanom
        pokazatelji = []
        for kolona in nazivi_numerickih:
            pokazatelji.append(pd.to_numeric(tabela[kolona], errors="coerce").isna().to_numpy(dtype=float))
            nazivi.append(f"{kolona}_nedostaje")
        delovi.append(np.column_stack(pokazatelji))

        # --- one-hot kodiranje, pisano ručno ---
        # ovo mi je isto što i pd.get_dummies sa vežbi, ali ručno: za svaku zapamćenu
        # vrednost pravim kolonu sa 1 ako je proizvod ima, inače 0; brend koji nije zadržan
        # ide u „ostalo", a nova vrednost ostalih kolona dobija sve nule
        one_hot, pokazatelji_kategorije = [], {}
        for kolona in self.kategoricke:
            if kolona not in tabela.columns:
                continue
            dozvoljene = self.vrednosti_kategorickih.get(kolona, [])
            vrednosti = tabela[kolona].astype(str)
            if "ostalo" in dozvoljene:
                vrednosti = vrednosti.where(vrednosti.isin(dozvoljene), "ostalo")
            for vrednost in dozvoljene:
                pokazatelj = (vrednosti == vrednost).to_numpy(dtype=float)
                one_hot.append(pokazatelj)
                nazivi.append(f"{kolona}={vrednost}")
                # pokazivače kategorije pamtim posebno, jer mi trebaju za interakcije
                if kolona == "kategorija":
                    pokazatelji_kategorije[vrednost] = pokazatelj
        # one-hot deo dodajem samo ako sam napravila bar jednu kolonu
        if one_hot:
            delovi.append(np.column_stack(one_hot))

        # --- članovi interakcije: kategorija × numerička karakteristika ---
        # Dodala sam ih jer bi bez njih 'zapremina_l' imala jedan koeficijent i za frižider
        # od 300 litara i za kuvalo za vodu od 2 litra, a litar zapremine kod njih ne vredi isto.
        if self.interakcije and pokazatelji_kategorije:
            interakcije = []
            for redni_broj, naziv_numericke in enumerate(nazivi_numerickih):
                for naziv_kategorije, pokazatelj in pokazatelji_kategorije.items():
                    # interakciju pravim tek posle standardizacije: kolona × pokazivač (0/1).
                    # Da sam standardizovala kolonu od skoro samih nula, std bi bila sitna,
                    # vrednosti ogromne i spust bi divergirao.
                    interakcije.append(standardizovane[:, redni_broj] * pokazatelj)
                    nazivi.append(f"{naziv_numericke}×{naziv_kategorije}")
            delovi.append(np.column_stack(interakcije))

        # hstack mi spaja sve delove u jednu matricu, redom kojim sam ih dodavala
        return np.hstack(delovi), nazivi

    # ---------------------------
    def kao_recnik(self) -> dict:
        """Vraća sve naučene parametre kao rečnik, da se priprema snimi u JSON zajedno sa modelom."""
        # sredine i odstupanja su numpy nizovi, pa ih sa tolist() pretvaram u liste za JSON
        return {
            "numericke":               self.numericke,
            "kategoricke":             self.kategoricke,
            "najmanje_po_brendu":      self.najmanje_po_brendu,
            "interakcije":             self.interakcije,
            "medijane_po_kategoriji":  self.medijane_po_kategoriji,
            "opste_medijane":          self.opste_medijane,
            "vrednosti_kategorickih":  self.vrednosti_kategorickih,
            "nazivi_kolona":           self.nazivi_kolona,
            "sredine":                 self.sredine.tolist(),
            "odstupanja":              self.odstupanja.tolist(),
        }

    @classmethod
    def iz_recnika(cls, podaci: dict) -> "Priprema":
        """
        Pravi objekat Priprema iz snimljenog JSON rečnika, bez ponovnog učenja.
        Tako aplikacija koristi iste medijane i standardizaciju kao pri obučavanju.
        """
        # prvo pravim objekat sa istim kolonama, pa mu umesto učenja upisujem snimljene parametre
        priprema = cls(podaci["numericke"], podaci["kategoricke"],
                       podaci["najmanje_po_brendu"], podaci["interakcije"])
        priprema.medijane_po_kategoriji = podaci["medijane_po_kategoriji"]
        priprema.opste_medijane = podaci["opste_medijane"]
        priprema.vrednosti_kategorickih = podaci["vrednosti_kategorickih"]
        priprema.nazivi_kolona = podaci["nazivi_kolona"]
        # sredine i odstupanja iz lista vraćam u numpy nizove, da deljenje radi po kolonama
        priprema.sredine = np.array(podaci["sredine"])
        priprema.odstupanja = np.array(podaci["odstupanja"])
        return priprema


# -------------------------------
# Podela na skup za treniranje i testiranje
# -------------------------------
def podeli(broj_redova: int, udeo_testa: float = 0.2, seme: int = 2026) -> tuple[np.ndarray, np.ndarray]:
    """
    Nasumično meša indekse redova i deli ih na trening i test; uz udeo_testa=0.2
    to je podela 80/20. Vraća dva niza indeksa. Seme je fiksno, pa je podela
    svaki put ista i rezultat može da se ponovi.
    """
    # default_rng sa semenom mi daje uvek isti redosled; permutation vraća sve indekse od 0 do
    # broj_redova − 1 izmešane. Prvi deo, udela 1 − udeo_testa (int zaokružuje naniže), ide u
    # trening, ostatak u test. Na vežbama je ovo radio train_test_split (test_size=0.25
    # i bez mešanja), a kod mene je 80/20 sa fiksnim semenom.
    generator = np.random.default_rng(seme)
    redosled = generator.permutation(broj_redova)
    granica = int(broj_redova * (1 - udeo_testa))
    return redosled[:granica], redosled[granica:]


if __name__ == "__main__":
    # ovde samo proveravam modul: pripremu učim na celoj tabeli, da vidim veličinu matrice
    tabela = ucitaj_preciscene()
    priprema = Priprema()
    X, nazivi = priprema.nauci_i_primeni(tabela)
    # ispisujem dimenzije matrice, prvih 12 naziva i broj one-hot kolona za brend
    print(f"[OK] Matrica obeležja: {X.shape[0]:,} redova × {X.shape[1]} kolona")
    print(f"[INFO] Prvih 12 obeležja: {', '.join(nazivi[:12])}")
    print(f"[INFO] Broj one-hot kolona za brend: "
          f"{sum(1 for n in nazivi if n.startswith('brend='))}")
