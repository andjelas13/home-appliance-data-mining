#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preporuke.py — Podsistem za preporučivanje zasnovan na sadržaju (Zadatak 6).

Opis:
Za izabrani proizvod skripta pronalazi njemu najsličnije proizvode iz iste
kategorije (podrazumevano pet). Profil proizvoda ima tri celine: numeričke
karakteristike standardizovane unutar kategorije, one-hot brend i TF-IDF nad
nazivom. Svaka celina se svodi na dužinu 1 i množi korenom težine (60%, 15%,
25%), pa je kosinusna sličnost celog profila težinski prosek sličnosti po
celinama. TF-IDF, skalarni proizvod i kosinusna sličnost su napisani ručno.

Ulazi:
    šema preciscena (preko modula podaci.py)

Izlazi:
    izvestaj/modeli/preporuke_primeri.txt   — primeri rada sistema za izveštaj (uz --primeri)
    konzola                                 — preporuke za proizvod zadat sa --trazi ili --id

Primer poziva:
    python preporuke.py --trazi "Gorenje kombinovani frižider"
    python preporuke.py --id 1234 --koliko 5
    python preporuke.py --primeri
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

# ubacujem models i kod u sys.path, da mi uvoz prođe bez obzira odakle pokrećem skriptu
sys.path.append(str(Path(__file__).resolve().parent))
from podaci import ucitaj_preciscene
sys.path.append(str(Path(__file__).resolve().parents[1]))
from zajednicko.putanje import FOLDER_MODELA

# Ovde sam popisala numeričke kolone koje mogu da uđu u profil; u kategoriji koristim
# samo one koje ima bar polovina proizvoda (vidi _numericki_blok).
NUMERICKA_OBELEZJA = [
    "cena_min", "dijagonala_inch", "zapremina_l", "zapremina_frizider_l",
    "zapremina_zamrzivac_l", "kapacitet_pranja_kg", "kapacitet_kompleta",
    "brzina_centrifuge", "snaga_w", "kapacitet_hladjenja_kw",
    "visina_cm", "sirina_cm", "dubina_cm", "tezina_kg", "gabarit_cm3",
    "energetska_rang",
]

# Težinske udele tri celine profila sam namestila da im je zbir 1. Tražim zamenu za
# uređaj, pa najviše nose cena i karakteristike, a brend najmanje; naziv sam stavila
# u sredinu jer krije podatke kojih nema u karakteristikama (npr. „inverter“, „no frost“).
TEZINE = {"numericka": 0.60, "brend": 0.15, "tekst": 0.25}

# U STOP_RECI sam stavila predloge, jedinice mere i slične reči iz naziva koje ne
# razlikuju jedan model od drugog. Jednoslovne reči ('i', 'u', 'l', 'w') nisam dodala,
# jer ih rastavi_na_reci ionako izbacuje.
STOP_RECI = {"za", "sa", "na", "od", "the", "cm", "kom", "kg"}

# ovim regularnim izrazom sve što nije malo slovo ili cifra uzimam kao granicu između reči
RASTAVLJANJE_RE = re.compile(r"[^a-z0-9]+")

# nazivi proizvoda čije preporuke prikazujem u izveštaju (slike aplikacije); i njih upisujem u
# preporuke_primeri.txt, da se brojevi iz izveštaja vide i bez aplikacije. Nazive prepisujem sa
# slika 7.1 i 7.2 iz izveštaja, da slika i fajl pokazuju isti proizvod.
PRIMERI_IZ_IZVESTAJA = ["Midea Inverter klima GAIA-12HRFN8-IG", "Gorenje Kombinovani frižider NRK11PWJ"]


# ============================================================================
# 1. OBRADA TEKSTA
# ============================================================================
def normalizuj(tekst: str) -> str:
    """Vraća tekst malim slovima i bez kvačica, da se 'Frižider' i 'frizider' računaju isto."""
    # 'đ' nema rastavljen oblik u Unicode-u, pa ga menjam sa 'dj' ručno
    tekst = str(tekst).lower().replace("đ", "dj")
    # NFKD mi rastavlja npr. 'ž' na 'z' i kvačicu, a kvačice zatim izbacujem
    razlozeno = unicodedata.normalize("NFKD", tekst)
    return "".join(z for z in razlozeno if not unicodedata.combining(z))


def rastavi_na_reci(tekst: str) -> list[str]:
    """
    Normalizuje naziv, deli ga na reči i vraća listu bez reči iz STOP_RECI i bez
    jednoslovnih reči. Oznake sa ciframa ('nrk61jsy2w', '55') ostaju, jer nose
    podatke o modelu i veličini.
    """
    # prvo normalizujem naziv i delim ga po RASTAVLJANJE_RE, bez praznih komada
    reci = [r for r in RASTAVLJANJE_RE.split(normalizuj(tekst)) if r]
    # zatim izbacujem stop reči i reči od jednog slova
    return [r for r in reci if r not in STOP_RECI and len(r) > 1]


# ============================================================================
# 2. TF-IDF — ručno napisan
# ============================================================================
class TfIdf:
    """
    Ručno napisan TF-IDF: iz naziva jedne kategorije uči rečnik i idf, a zatim
    svaki naziv pretvara u vektor (jedna kolona po reči iz rečnika).

        tf(t, d)   = broj pojavljivanja reči t u nazivu d / ukupan broj reči u d
        idf(t)     = ln( N / (1 + df(t)) ) + 1
        tfidf(t,d) = tf(t, d) · idf(t)

    N je broj naziva, a df(t) broj naziva u kojima se javlja reč t. Česta reč
    ('televizor' među televizorima) dobija malu težinu, a retka ('oled',
    'inverter') veliku, jer bolje razlikuje proizvode. Jedinica na kraju čuva da
    idf bude pozitivan: bez nje bi reč iz svih naziva dobila ln(N / (N + 1)) < 0.
    Jedinica u imeniocu je izglađivanje; deljenja nulom nema ni bez nje, jer
    rečnik ima samo reči koje se javljaju bar u jednom nazivu.
    """

    def __init__(self):
        # na početku nemam ni rečnik ni idf; njih popunjavam u metodi nauci
        self.recnik: dict[str, int] = {}     # reč -> redni broj kolone
        self.idf: np.ndarray | None = None

    def nauci(self, nazivi: list[str]) -> None:
        """Rastavlja nazive na reči, pravi rečnik (reč → kolona) i računa idf svake reči."""
        # svaki naziv mi je jedan dokument, već rastavljen na reči
        dokumenti = [rastavi_na_reci(n) for n in nazivi]
        broj_dokumenata = len(dokumenti)

        # df mi je broj naziva u kojima se reč javlja; set() stavljam da reč ponovljenu
        # u istom nazivu brojim samo jednom
        pojavljivanje = Counter()
        for reci in dokumenti:
            pojavljivanje.update(set(reci))

        # reči sortiram, pa svaka reč uvek dobija istu kolonu
        self.recnik = {rec: i for i, rec in enumerate(sorted(pojavljivanje))}
        self.idf = np.zeros(len(self.recnik))
        # za svaku reč iz rečnika računam idf = ln(N / (1 + df)) + 1
        for rec, redni_broj in self.recnik.items():
            self.idf[redni_broj] = math.log(broj_dokumenata / (1 + pojavljivanje[rec])) + 1.0

    def vektor(self, naziv: str) -> np.ndarray:
        """
        Pravi TF-IDF vektor jednog naziva: za svaku reč iz rečnika upisuje tf · idf,
        a reč koje nema u rečniku preskače. Naziv bez reči daje nula-vektor.
        """
        # krećem od nula-vektora dugog koliko i rečnik
        vektor = np.zeros(len(self.recnik))
        reci = rastavi_na_reci(naziv)
        # bez ove provere bih ispod delila sa len(reci), a ono je tada nula
        if not reci:
            return vektor

        # Counter mi broji koliko se puta svaka reč javlja u nazivu, a tf je taj broj kroz
        # len(reci); recnik.get mi vraća None za reč koju nisam videla u nauci
        brojac = Counter(reci)
        for rec, broj in brojac.items():
            redni_broj = self.recnik.get(rec)
            if redni_broj is not None:
                vektor[redni_broj] = (broj / len(reci)) * self.idf[redni_broj]
        return vektor

    def matrica(self, nazivi: list[str]) -> np.ndarray:
        """
        Slaže TF-IDF vektore naziva u matricu, jedan red po nazivu; za prazan spisak
        vraća praznu matricu.
        """
        # np.vstack ne prima prazan spisak, pa za prazne nazive sama pravim matricu
        # sa 0 redova i onoliko kolona koliko rečnik ima reči
        return np.vstack([self.vektor(n) for n in nazivi]) if nazivi else np.zeros((0, len(self.recnik)))


# ============================================================================
# 3. KOSINUSNA SLIČNOST — ručno napisana
# ============================================================================
def skalarni_proizvod(a, b) -> float:
    """
    Računa skalarni proizvod dva vektora, a · b = a₁·b₁ + a₂·b₂ + ... + aₙ·bₙ.
    Napisala sam ga običnom petljom, bez numpy.dot i operatora @, jer zadatak 6
    traži da se formula za skalarni proizvod kodira ručno.
    """
    # u petlji sabiram proizvode koordinata koje stoje na istom mestu u oba vektora
    zbir = 0.0
    for x, y in zip(a, b):
        zbir += x * y
    return zbir


def intenzitet(vektor) -> float:
    """
    Vraća intenzitet (dužinu) vektora, ‖v‖ = √(v₁² + v₂² + ... + vₙ²). Zbir
    kvadrata je skalarni proizvod vektora sa samim sobom, pa koristim istu ručnu
    funkciju skalarni_proizvod.
    """
    # intenzitet mi treba i u kosinusnoj sličnosti i u _spoji_blokove, gde njime delim svaki red
    return math.sqrt(skalarni_proizvod(vektor, vektor))


def kosinusna_slicnost(a, b) -> float:
    """
    Računa kosinus ugla između vektora a i b: cos(a, b) = (a · b) / (‖a‖ · ‖b‖).
    Deljenjem intenzitetima rezultat zavisi samo od smera, a ne od veličine vrednosti.
    Vrednost 1 znači isti smer, 0 da vektori nemaju ništa zajedničko (normalni su),
    a negativna da su suprotni, što je moguće zbog standardizovanih numeričkih kolona.
    """
    # ako je neki vektor nula, ugao nije definisan, pa umesto deljenja nulom vraćam 0
    imenilac = intenzitet(a) * intenzitet(b)
    return skalarni_proizvod(a, b) / imenilac if imenilac > 0 else 0.0


def kosinusna_slicnost_prema_svima(jedan, svi) -> np.ndarray:
    """
    Vraća niz kosinusnih sličnosti jednog vektora prema svakom redu matrice svi.
    Za svaki red poziva istu ručnu funkciju kosinusna_slicnost, bez ubrzane verzije.
    Redove pretvaram u Python liste, jer je petlja nad listom brža nego nad numpy
    nizom. Za televizore, najveću kategoriju (1.895 proizvoda, profil sa 2.070
    kolona), jedan poziv prođe kroz blizu četiri miliona množenja i traje od pola
    sekunde do sekunde i po, zavisno od računara.
    """
    # polazni vektor pretvaram u listu samo jednom, van petlje
    polazni = jedan.tolist() if hasattr(jedan, "tolist") else list(jedan)
    # za svaki red matrice svi pozivam svoju kosinusna_slicnost i sve pakujem u numpy niz
    return np.array([kosinusna_slicnost(polazni, red.tolist() if hasattr(red, "tolist") else list(red))
                     for red in svi])



# ============================================================================
# 4. SISTEM PREPORUKA
# ============================================================================
class SistemPreporuka:
    """
    Gradi profile proizvoda posebno za svaku kategoriju i za izabrani proizvod
    vraća najsličnije iz iste kategorije. Zato i standardizacija i TF-IDF rade
    unutar kategorije: među frižiderima je reč „frizider“ česta i skoro ništa ne
    govori, a među svim uređajima bi dobro razlikovala proizvode.
    """

    def __init__(self, tabela: pd.DataFrame, tezine: dict | None = None):
        """Pamti tabelu i težine (podrazumevano TEZINE) i odmah gradi profile."""
        # indekse tabele resetujem, a težine kopiram u novi rečnik, da ne diram globalni TEZINE
        self.tabela = tabela.reset_index(drop=True)
        self.tezine = dict(tezine or TEZINE)
        self.po_kategoriji: dict[str, dict] = {}
        # profile gradim odmah, pa mi je sistem spreman čim ga napravim
        self._izgradi()

    # ---------------------------
    def _izgradi(self) -> None:
        """
        Za svaku kategoriju sa bar šest proizvoda pravi numerički blok, brend blok i
        TF-IDF blok, spaja ih u matricu profila i pamti je u po_kategoriji.
        """
        # profile pravim posebno za svaku kategoriju, preko groupby
        for kategorija, deo in self.tabela.groupby("kategorija"):
            deo = deo.reset_index(drop=True)
            if len(deo) < 6:            # uz sam proizvod treba još pet za preporuku
                continue

            # numerički i brend blok pravim nad istom tabelom deo, pa im se redovi poklapaju
            numericka = self._numericki_blok(deo)
            brend = self._brend_blok(deo)

            # brend izbacujem iz naziva pre TF-IDF-a, inače bi se brojao dvaput (kroz
            # one-hot blok i kroz reč 'Gorenje' u nazivu) i nosio bi više od zadatih 15%
            nazivi_bez_brenda = [
                self._izbaci_brend(naziv, brend_naziv)
                for naziv, brend_naziv in zip(deo["naziv"].astype(str), deo["brend"].astype(str))
            ]

            # TF-IDF-u dajem da nauči rečnik i idf samo iz naziva ove kategorije
            tfidf = TfIdf()
            tfidf.nauci(nazivi_bez_brenda)
            tekst = tfidf.matrica(nazivi_bez_brenda)

            # tri bloka spajam u jednu matricu profila, jedan red po proizvodu
            profili = self._spoji_blokove(numericka, brend, tekst)

            # tabelu i profile pamtim zajedno, jer isti redni broj u tabeli deo i u matrici
            # profili pripada istom proizvodu
            self.po_kategoriji[kategorija] = {
                "tabela":  deo,
                "profili": profili,
            }

    # ---------------------------
    @staticmethod
    def _izbaci_brend(naziv: str, brend: str) -> str:
        """
        Vraća naziv iz koga je izbačeno ime brenda, bez obzira na velika i mala slova.
        Ako brend nije poznat, naziv ostaje isti.
        """
        # prazan brend podaci.py upisuje kao „nepoznat“, pa i njega preskačem
        if not brend or brend.lower() == "nepoznat":
            return naziv
        # re.escape mi treba jer ime brenda može da ima tačku ili crticu; brend menjam razmakom
        return re.sub(re.escape(brend), " ", naziv, flags=re.IGNORECASE)

    def _numericki_blok(self, deo: pd.DataFrame) -> np.ndarray:
        """
        Vraća numeričke karakteristike standardizovane unutar kategorije. Uzima samo
        kolone koje ima bar polovina proizvoda, a nedostajuće vrednosti popunjava
        medijanom kategorije, jer sličnost mora da se izračuna i za nepotpune zapise.
        """
        kolone = []
        # prolazim kroz sve moguće numeričke kolone i zadržavam samo one koje razlikuju proizvode
        for obelezje in NUMERICKA_OBELEZJA:
            if obelezje not in deo.columns:
                continue
            vrednosti = pd.to_numeric(deo[obelezje], errors="coerce")
            # kolonu koju ima manje od pola proizvoda preskačem, jer bi posle popune bila
            # uglavnom medijana i ne bi razlikovala proizvode
            if vrednosti.notna().mean() < 0.5:
                continue
            # prazna polja popunjavam medijanom kategorije, jer na nju malo utiču skupi uređaji
            medijana = vrednosti.median()
            popunjeno = vrednosti.fillna(medijana).to_numpy(dtype=float)
            odstupanje = popunjeno.std()
            if odstupanje == 0:             # ista vrednost kod svih ništa ne razlikuje
                continue
            # z-vrednost računam kao (x − prosek) / standardna devijacija
            kolone.append((popunjeno - popunjeno.mean()) / odstupanje)

        # ako mi nijedna kolona ne prođe, vraćam blok od jedne kolone nula
        return np.column_stack(kolone) if kolone else np.zeros((len(deo), 1))

    def _brend_blok(self, deo: pd.DataFrame) -> np.ndarray:
        """
        Ručno pravi one-hot matricu brenda: jedan red po proizvodu, jedna kolona po
        brendu, sa jedinicom u koloni brenda tog proizvoda i nulama svuda drugde.
        """
        # brendove sortiram, pa svaki brend ima stalnu kolonu
        brendovi = sorted(deo["brend"].astype(str).unique())
        redosled = {brend: i for i, brend in enumerate(brendovi)}
        # krećem od matrice nula i svakom proizvodu upisujem jedinicu u kolonu njegovog brenda
        matrica = np.zeros((len(deo), len(brendovi)))
        for redni_broj, brend in enumerate(deo["brend"].astype(str)):
            matrica[redni_broj, redosled[brend]] = 1.0
        return matrica

    def _spoji_blokove(self, numericka: np.ndarray, brend: np.ndarray,
                       tekst: np.ndarray) -> np.ndarray:
        """
        Svaki blok svodi red po red na dužinu 1, množi ga korenom njegove težine i
        spaja blokove u matricu profila. Koren je tu jer skalarni proizvod množi dva
        profila, pa √w·√w daje w; ukupna dužina profila je 1 (zbir težina je 1) i
        kosinus celog profila postaje težinski prosek:

            cos(A, B) = w_num·cos_num + w_brend·cos_brend + w_tekst·cos_tekst
        """
        delovi = []
        # blokove obrađujem redom (numerički, brend, tekst), svaki sa svojom težinom iz self.tezine
        for blok, kljuc in ((numericka, "numericka"), (brend, "brend"), (tekst, "tekst")):
            if blok.size == 0:              # npr. TF-IDF bez ijedne reči u rečniku
                continue
            # dužinu svakog reda računam istom ručnom funkcijom intenzitet(); red koji
            # je ceo nula dobija dužinu 1, da se ne deli nulom, i ostaje nula
            duzine = np.array([[intenzitet(red.tolist())] for red in blok])
            duzine[duzine == 0] = 1.0
            # svaki red delim njegovom dužinom i množim korenom težine bloka
            delovi.append((blok / duzine) * math.sqrt(self.tezine.get(kljuc, 0.0)))
        # blokove spajam jedan pored drugog, po kolonama
        return np.hstack(delovi)

    # ---------------------------
    def pretrazi(self, tekst: str, koliko: int = 20) -> pd.DataFrame:
        """
        Vraća najviše `koliko` proizvoda čiji naziv sadrži svaku reč zadatog teksta,
        bilo kojim redom. I naziv i tekst se prvo normalizuju, pa kvačice i velika
        slova ne smetaju, a reč se traži i u nazivu bez razmaka („RF212EPW4“). Znaci
        interpunkcije razdvajaju reči, pa i „frižider,“ nađe frižidere.
        """
        # normalizujem sve nazive, a od svakog pravim i oblik bez razmaka
        nazivi = self.tabela["naziv"].astype(str).map(normalizuj)
        bez_razmaka = nazivi.str.replace(" ", "", regex=False)
        # reči izdvajam istim obrascem kao rastavi_na_reci, da zalepljen zarez ili zagrada ne
        # ostane deo reči; jednoslovne reči i stop reči ovde zadržavam, jer se u pretrazi traže
        # kao deo naziva, a upit u kom nema ni jedne reči nema ni pogodak
        reci = [rec for rec in RASTAVLJANJE_RE.split(normalizuj(tekst)) if rec]
        if not reci:
            return self.tabela.iloc[:0]
        # krećem od „svi pogađaju“ i za svaku reč zadržavam samo nazive koji je sadrže;
        # regex=False jer reč tražim kao običan tekst, a ne kao regularni izraz
        pogodak = pd.Series(True, index=nazivi.index)
        for rec in reci:
            pogodak &= nazivi.str.contains(rec, regex=False) | bez_razmaka.str.contains(rec, regex=False)
        # vraćam samo prvih koliko pogodaka
        return self.tabela[pogodak].head(koliko)

    def oznaka_uredjaja(self, red: pd.Series) -> tuple:
        """
        Vraća brend i sortiran spisak svih grupa slova i cifara iz naziva bez brenda
        („TM1057“ i „TM 1057“ daju isto: 1057, tm). Dva proizvoda sa istom oznakom
        smatram istim uređajem (npr. isti model upisan iz dve prodavnice).
        """
        brend = str(red["brend"])
        naziv = normalizuj(self._izbaci_brend(str(red["naziv"]), brend))
        # rastavi_na_reci ovde ne koristim, jer izbacuje jednoslovne reči, a „W“ i „B“ (boja)
        # ili „2“ i „3“ u oznaci modela razlikuju uređaje; „outlet“ je oznaka akcije u
        # prodavnici, a ne uređaja, pa je u ključ ne uzimam
        return brend.lower(), tuple(sorted(x for x in re.findall(r"[a-z]+|[0-9]+", naziv)
                                           if x != "outlet"))

    def preporuci(self, proizvod_id: int, koliko: int = 5) -> pd.DataFrame:
        """
        Za proizvod sa zadatim id-jem računa kosinusnu sličnost prema svim profilima
        njegove kategorije i vraća `koliko` najsličnijih, od najsličnijeg naniže, sa
        kolonom slicnost. Preskače sam proizvod i uređaje koji su isti kao neki već
        uzet (vidi oznaka_uredjaja), pa vraća manje od `koliko` samo kad nema dovoljno drugih.
        """
        # prvo tražim proizvod po id-ju i javljam grešku ako ga nema
        red = self.tabela[self.tabela["id"] == proizvod_id]
        if red.empty:
            raise ValueError(f"Ne postoji proizvod sa id={proizvod_id}")
        kategorija = red.iloc[0]["kategorija"]

        # kategorija sa manje od šest proizvoda nije ni ušla u po_kategoriji
        if kategorija not in self.po_kategoriji:
            raise ValueError(f"Kategorija '{kategorija}' ima premalo proizvoda za preporuku.")

        podaci = self.po_kategoriji[kategorija]
        deo, profili = podaci["tabela"], podaci["profili"]

        # redni broj proizvoda u tabeli kategorije mi je ujedno red njegovog profila
        mesto = int(deo.index[deo["id"] == proizvod_id][0])

        # računam kosinusnu sličnost polaznog profila prema svim profilima kategorije
        slicnosti = kosinusna_slicnost_prema_svima(profili[mesto], profili)
        slicnosti[mesto] = -np.inf              # proizvod ne preporučujem samom sebi

        # argsort nad -slicnosti mi daje redosled od najveće sličnosti ka najmanjoj. Idem tim
        # redom i uzimam proizvod samo ako njegov uređaj još nisam videla; polazni uređaj
        # stavljam u vidjene odmah, pa ne preporučujem ni njegov duplikat
        vidjeni = {self.oznaka_uredjaja(deo.iloc[mesto])}
        najbolji = []
        for indeks in np.argsort(-slicnosti):
            if len(najbolji) == koliko:
                break
            oznaka = self.oznaka_uredjaja(deo.iloc[indeks])
            if oznaka not in vidjeni:
                vidjeni.add(oznaka)
                najbolji.append(indeks)
        # izabranim proizvodima dopisujem kolonu slicnost
        rezultat = deo.iloc[najbolji].copy()
        rezultat["slicnost"] = slicnosti[najbolji]
        return rezultat.reset_index(drop=True)


# ============================================================================
# 5. ISPIS I PRIMERI
# ============================================================================
def ispisi_preporuke(sistem: SistemPreporuka, proizvod_id: int, koliko: int = 5) -> str:
    """
    Sastavlja tekstualnu tabelu sa polaznim proizvodom i njegovim preporukama
    (sličnost, cena, brend, naziv) i vraća je kao jedan tekst.
    """
    # preporuke tražim prvo, jer preporuci() za nepostojeći id javlja jasnu grešku
    preporuke = sistem.preporuci(proizvod_id, koliko)
    polazni = sistem.tabela[sistem.tabela["id"] == proizvod_id].iloc[0]

    # zaglavlje sa podacima o polaznom proizvodu i nazivima kolona
    redovi = [
        "=" * 100,
        f"POLAZNI PROIZVOD: {polazni['naziv']}",
        f"   kategorija: {polazni['kategorija']}   brend: {polazni['brend']}   "
        f"cena: {int(polazni['cena_min']):,} RSD".replace(",", "."),
        "-" * 100,
        f"{'#':<3} {'sličnost':>9}  {'cena (RSD)':>12}  {'brend':<14} naziv",
        "-" * 100,
    ]
    # svaku preporuku pišem u jedan red; brend skraćujem na 14, a naziv na 52 znaka.
    # Sličnost pišem sa decimalnim zarezom, a cenu sa tačkom za hiljade, kako se piše na
    # srpskom, da se u istom redu vidi koja je tačka razdvajač hiljada
    for redni_broj, (_, red) in enumerate(preporuke.iterrows(), start=1):
        cena = f"{int(red['cena_min']):,}".replace(",", ".")
        slicnost = f"{red['slicnost']:.4f}".replace(".", ",")
        redovi.append(f"{redni_broj:<3} {slicnost:>9}  {cena:>12}  "
                      f"{str(red['brend'])[:14]:<14} {str(red['naziv'])[:52]}")
    redovi.append("=" * 100)
    return "\n".join(redovi)


def napravi_primere(sistem: SistemPreporuka) -> None:
    """
    Za frižider, televizor, veš-mašinu i klimu bira proizvod sa najviše popunjenih
    karakteristika, ispisuje njegove preporuke i sve snima u preporuke_primeri.txt.
    """
    FOLDER_MODELA.mkdir(parents=True, exist_ok=True)
    delovi = []

    # primere pravim za ove četiri kategorije, ako su dovoljno velike za preporuku
    for kategorija in ["frizider", "televizor", "ves_masina", "klima"]:
        deo = sistem.tabela[sistem.tabela["kategorija"] == kategorija]
        if deo.empty or kategorija not in sistem.po_kategoriji:
            continue
        # za primer uzimam proizvod sa najviše popunjenih karakteristika, da profil bude potpun
        najpotpuniji = deo.sort_values("broj_karakteristika", ascending=False).iloc[0]
        ispis = ispisi_preporuke(sistem, int(najpotpuniji["id"]))
        print(ispis + "\n")
        delovi.append(ispis)

    # zatim primeri iz izveštaja, koje tražim po normalizovanom nazivu, da velika slova i
    # kvačice iz druge prodavnice ne promaše
    for naziv in PRIMERI_IZ_IZVESTAJA:
        trazeno = normalizuj(naziv)
        nadjeni = sistem.tabela[sistem.tabela["naziv"].astype(str).map(normalizuj) == trazeno]
        if nadjeni.empty:
            print(f"[UPOZORENJE] Nema proizvoda sa nazivom '{naziv}'")
            continue
        ispis = ispisi_preporuke(sistem, int(nadjeni.iloc[0]["id"]))
        print(ispis + "\n")
        delovi.append(ispis)

    # u fajl upisujem zaglavlje sa težinama i sve primere, razdvojene praznim redom
    putanja = FOLDER_MODELA / "preporuke_primeri.txt"
    zaglavlje = (
        "PRIMERI RADA PODSISTEMA ZA PREPORUČIVANJE (Zadatak 6)\n"
        f"Težinski udeli: numeričke karakteristike {TEZINE['numericka']:.0%}, "
        f"brend {TEZINE['brend']:.0%}, naziv {TEZINE['tekst']:.0%}\n"
        "Mera sličnosti: kosinusna sličnost, ručno implementirana.\n\n"
    )
    putanja.write_text(zaglavlje + "\n\n".join(delovi), encoding="utf-8")
    print(f"[OK] Primeri snimljeni: {putanja}")


# ============================================================================
# Glavni program
# ============================================================================
def main() -> None:
    """
    Čita opcije, gradi sistem preporuka i ispisuje rezultat pretrage, preporuke za
    zadati id ili primere za izveštaj.
    """
    # opcije su --trazi, --id, --koliko i --primeri
    parser = argparse.ArgumentParser(description="Podsistem za preporučivanje proizvoda.")
    parser.add_argument("--trazi", default=None, help="pretraga proizvoda po nazivu")
    parser.add_argument("--id", type=int, default=None, help="id proizvoda za koji se traže preporuke")
    parser.add_argument("--koliko", type=int, default=5, help="broj preporuka")
    parser.add_argument("--primeri", action="store_true", help="napraviti primere za izveštaj")
    argumenti = parser.parse_args()

    # učitavam prečišćene proizvode i gradim profile za sve kategorije
    tabela = ucitaj_preciscene()
    sistem = SistemPreporuka(tabela)
    print(f"[INFO] Profili izgrađeni za {len(sistem.po_kategoriji)} kategorija")

    # sa --primeri pravim samo primere za izveštaj i izlazim
    if argumenti.primeri:
        napravi_primere(sistem)
        return

    # pretraga po nazivu mi ispisuje pronađene proizvode sa id-jem i cenom
    if argumenti.trazi:
        # prvo brojim sve pogotke, pa prikazujem samo prvih dvadeset, kao i aplikacija
        svi_pogoci = sistem.pretrazi(argumenti.trazi, len(sistem.tabela))
        if svi_pogoci.empty:
            print(f"[INFO] Nema proizvoda čiji naziv sadrži '{argumenti.trazi}'")
            return
        nadjeni = svi_pogoci.head(20)
        print(f"[INFO] Pronađeno proizvoda: {len(svi_pogoci)}, prikazujem {len(nadjeni)}")
        for _, red in nadjeni.iterrows():
            cena = f"{int(red['cena_min']):,}".replace(",", ".")
            print(f"   id={red['id']:<6} {cena:>10} RSD  {str(red['naziv'])[:70]}")
        # ako --id nije zadat, preporuke tražim za prvi pronađeni proizvod
        argumenti.id = argumenti.id or int(nadjeni.iloc[0]["id"])
        print()

    # kad imam id, ispisujem preporuke, a inače podsećam kako se skripta pokreće
    if argumenti.id:
        try:
            print(ispisi_preporuke(sistem, argumenti.id, argumenti.koliko))
        except ValueError as greska:
            print(f"[GRESKA] {greska}")
    else:
        print("[INFO] Zadaj --trazi ili --id, ili pokreni sa --primeri")


if __name__ == "__main__":
    main()
