#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kmeans.py — Klasterovanje proizvoda algoritmom K-srednjih vrednosti (Zadatak 5).

Opis:
Skripta učitava prečišćene proizvode, uzima obeležja, težine i broj klastera K
koje je zadao korisnik i pravi standardizovanu matricu sa težinama. Nad njom
pokreće ručno napisan K-means: početni centri po k-means++, dodela najbližem
centru i pomeranje centara dok se dodela ne ustali. Algoritam pokreće deset puta,
sa različitim početnim centrima, i zadržava rešenje sa najmanjom inercijom.
Kvalitet ocenjuje inercijom i Silhouette koeficijentom, a svaki klaster opisuje
kratkom rečenicom. Rezultate snima u CSV fajlove i crta grafikone.

Ulazi:
    šema preciscena (preko modula podaci.py)

Izlazi:
    izvestaj/modeli/kmeans_rezultat.csv        — pripadnost klasteru po proizvodu
    izvestaj/modeli/kmeans_opis.csv            — opis svakog klastera
    izvestaj/modeli/kmeans_ocena.csv           — podešavanje, inercija i Silhouette
    izvestaj/modeli/kmeans_lakat.csv           — inercija i Silhouette za K od 2 do 10 (uz --lakat)
    izvestaj/grafikoni/10_kmeans_lakat.png     — izbor broja klastera (uz --lakat)
    izvestaj/grafikoni/11_kmeans_rasipanje.png — dijagram rasipanja po klasterima
    izvestaj/grafikoni/12_kmeans_velicine.png  — broj proizvoda po klasteru

Primer poziva:
    python kmeans.py --kategorija frizider --k 4 --obelezja cena_min,zapremina_l,energetska_rang --tezine 50,30,20
    python kmeans.py --kategorija frizider --obelezja cena_min,zapremina_l,energetska_rang --tezine 50,30,20 --lakat
    python kmeans.py --kategorija televizor --k 5 --obelezja cena_min,dijagonala_inch --tezine 60,40
    (prva dva poziva su podešavanje iz izveštaja; njih pokreće i pokreni.bat)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
# grafikone crtam direktno u fajl, bez otvaranja prozora, pa zato biram Agg
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

# dodajem foldere models i kod u putanju, da mi uvoz radi odakle god pokrenem skriptu
sys.path.append(str(Path(__file__).resolve().parent))
from podaci import ucitaj_preciscene
sys.path.append(str(Path(__file__).resolve().parents[1]))
from zajednicko.putanje import FOLDER_MODELA, FOLDER_GRAFIKONA
from zajednicko import nazivi

# boje grafikona su iste kao u grafikoni.py: bordo je osnovna, a oker mi služi za naglasak
BORDO, TAMNI_BORDO, OKER = "#7A1F3D", "#4E1226", "#C47A93"
TAMNI_OKER = "#8C5A6B"          # oker za tekst, jer se svetli oker slabo čita na svetloj podlozi
POZADINA, TEKST = "#FBF4F6", "#2B2024"
IVICA, MREZA = "#8C6A76", "#C9A3B0"

# za sve grafikone sam podesila Times New Roman, ujednačene veličine slova i bordo izgled
plt.rcParams.update({
    "font.family": "Times New Roman",
    "axes.titlesize": 15, "axes.titleweight": "bold", "axes.titlecolor": TAMNI_BORDO,
    "axes.titlepad": 10, "axes.labelsize": 13, "axes.labelcolor": TEKST,
    "axes.edgecolor": IVICA, "axes.facecolor": POZADINA, "figure.facecolor": POZADINA,
    "text.color": TEKST, "xtick.color": IVICA, "ytick.color": IVICA,
    "xtick.labelcolor": TEKST, "ytick.labelcolor": TEKST,
    "grid.color": MREZA, "legend.edgecolor": MREZA,
    "xtick.labelsize": 12, "ytick.labelsize": 12, "legend.fontsize": 12,
    "figure.dpi": 120, "savefig.bbox": "tight",
})

# boje sam poređala redom po klasteru; ima ih 12, koliko najviše klastera dozvoljava aplikacija,
# a istu listu koristi i app.py za grafikon u prozoru aplikacije, da klaster sa istim rednim
# brojem svuda ima istu boju.
# Prva je bordo, a ostale su jasno različiti tonovi (oker, škriljac, maslinasta, ruža...),
# poređani tako da se i susedne boje, i prve četiri međusobno, lako razlikuju.
BOJE = ["#7A1F3D", "#D98BA0", "#6E6E6E", "#4E1226", "#B23A5B", "#BFA6AE",
        "#2B2024", "#9E7B88", "#E8C9D3", "#8C8C8C", "#C4607E", "#5C3A47"]

# Ovde sam popisala obeležja među kojima korisnik bira, uz naziv za formu i ose grafikona.
DOSTUPNA_OBELEZJA = {
    "cena_min":                 "Cena",
    "dijagonala_inch":          "Dijagonala ekrana (inč)",
    "zapremina_l":              "Zapremina (l)",
    "zapremina_frizider_l":     "Zapremina frižidera (l)",
    "zapremina_zamrzivac_l":    "Zapremina zamrzivača (l)",
    "kapacitet_pranja_kg":      "Kapacitet pranja (kg)",
    "kapacitet_kompleta":       "Kapacitet (kompleta posuđa)",
    "brzina_centrifuge":        "Brzina centrifuge (obr/min)",
    "snaga_w":                  "Snaga (W)",
    "kapacitet_hladjenja_kw":   "Rashladni učinak (kW)",
    "visina_cm":                "Visina (cm)",
    "sirina_cm":                "Širina (cm)",
    "dubina_cm":                "Dubina (cm)",
    "tezina_kg":                "Težina (kg)",
    "nivo_buke_db":             "Nivo buke (dB)",
    "gabarit_cm3":              "Gabarit (cm³)",
    "energetska_rang":          "Energetska klasa (rang, 1 = najbolja)",
    "cena_po_incu":             "Cena po inču",
    "cena_po_litru":            "Cena po litru",
    "cena_po_kw_hladjenja":     "Cena po kW rashladnog učinka",
}


# Kraće nazive bez jedinica mere koristim u rečenici opisa klastera („veća zapremina“).
OPISNI_NAZIVI = {
    "dijagonala_inch":        "dijagonala",
    "zapremina_l":            "zapremina",
    "zapremina_frizider_l":   "zapremina frižidera",
    "zapremina_zamrzivac_l":  "zapremina zamrzivača",
    "kapacitet_pranja_kg":    "kapacitet",
    "kapacitet_kompleta":     "kapacitet",
    "brzina_centrifuge":      "brzina centrifuge",
    "snaga_w":                "snaga",
    "kapacitet_hladjenja_kw": "rashladni učinak",
    "visina_cm":              "visina",
    "sirina_cm":              "širina",
    "dubina_cm":              "dubina",
    "tezina_kg":              "težina",
    "nivo_buke_db":           "nivo buke",
    "gabarit_cm3":            "gabarit",
    "cena_po_incu":           "cena po inču",
    "cena_po_litru":          "cena po litru",
    "cena_po_kw_hladjenja":   "cena po kW",
}

# Pragove za opis klastera rečima (sastavi_recenicu) sam izdvojila ovde. PRAG_* mi je
# odnos proseka klastera i proseka skupa sa kojim poredim (1,3 znači 30% iznad), a
# UDEO_* je udeo proizvoda unutar klastera.
PRAG_CENA_ZNATNO_SKUPLJI    = 2.0
PRAG_CENA_SKUPLJI           = 1.3
PRAG_CENA_ZNATNO_JEFTINIJI  = 0.5
PRAG_CENA_JEFTINIJI         = 0.7
PRAG_ZNATNO_VECI            = 1.6
PRAG_VECI                   = 1.25
PRAG_ZNATNO_MANJI           = 0.6
PRAG_MANJI                  = 0.75
PRAG_BOLJA_KLASA            = 0.85
PRAG_LOSIJA_KLASA           = 1.15
UDEO_PRETEZNE_KATEGORIJE    = 0.6
UDEO_JEDNE_SKALE            = 0.8
UDEO_SA_ENERGETSKOM_KLASOM  = 0.5
NAJVISE_DELOVA_OPISA        = 4       # pre dodavanja energetske klase


def decimalno(vrednost: float, decimala: int) -> str:
    """
    Vraća broj sa tačkom za hiljade i zarezom za decimale (1.112 i 339,7), za ispis u konzoli.
    Isti postupak ima i funkcija broj u app.py, ali ovaj modul radi i sam iz komandne linije,
    pa formatiranje držim u njemu.
    """
    # zarez za hiljade privremeno menjam sa #, da se ne pomeša sa decimalnom tačkom koja postaje zarez
    return f"{vrednost:,.{decimala}f}".replace(",", "#").replace(".", ",").replace("#", ".")


# ============================================================================
# 1. PRIPREMA ULAZA
# ============================================================================
def pripremi_matricu(tabela: pd.DataFrame, obelezja: list[str],
                     tezine: list[float]) -> tuple[np.ndarray, pd.DataFrame]:
    """
    Funkcija uzima izabrane kolone, izbacuje proizvode kojima fali neka od njih,
    standardizuje vrednosti i primenjuje težine. Vraća matricu za K-means i
    tabelu zadržanih proizvoda.
    """
    # prvo proveravam da za svako obeležje imam tačno jednu težinu
    if len(obelezja) != len(tezine):
        raise ValueError("Broj obeležja i broj težina se ne poklapaju.")

    # proizvod kome fali bilo koja izabrana vrednost izostavljam, umesto da je
    # popunim medijanom: izmišljena vrednost bi ga veštački privukla nekom klasteru
    deo = tabela[obelezja].apply(pd.to_numeric, errors="coerce")
    potpuni = deo.notna().all(axis=1)
    zadrzani = tabela[potpuni].reset_index(drop=True)
    vrednosti = deo[potpuni].to_numpy(dtype=float)

    # ako ostane manje od deset proizvoda, nemam šta smisleno da delim u klastere
    if len(zadrzani) < 10:
        raise ValueError(f"Samo {len(zadrzani)} proizvoda ima sve izabrane "
                         f"karakteristike — premalo za klasterovanje.")

    # 1) svaku kolonu svodim na z-vrednost, da mi zapremina u stotinama litara ne
    #    nadjača energetski rang od 1 do 7; koloni u kojoj su sve vrednosti iste
    #    stavljam odstupanje 1, da ne delim nulom. Ovo mi je kao MinMaxScaler sa
    #    vežbi, samo ručno i sa z-vrednošću umesto opsega 0–1
    sredine = vrednosti.mean(axis=0)
    odstupanja = vrednosti.std(axis=0)
    odstupanja[odstupanja == 0] = 1.0
    standardizovano = (vrednosti - sredine) / odstupanja

    # 2) težine svodim na zbir 1, a kolonu množim korenom težine: rastojanje kvadrira
    #    razliku, pa mi se √w vraća na w, tj. d² = Σ wⱼ·(xⱼ − cⱼ)²
    udeli = np.array(tezine, dtype=float)
    if udeli.sum() <= 0:
        raise ValueError("Zbir težina mora biti veći od nule.")
    udeli = udeli / udeli.sum()                 # sada je zbir udela 1
    matrica = standardizovano * np.sqrt(udeli)

    return matrica, zadrzani


# ============================================================================
# 2. ALGORITAM K-SREDNJIH VREDNOSTI — ručno napisan
# ============================================================================
def rastojanja_do_centara(X: np.ndarray, centri: np.ndarray) -> np.ndarray:
    """
    Računa kvadrat euklidskog rastojanja od svake tačke do svakog centra i vraća
    matricu oblika (broj tačaka × broj centara). Koren ne vadim, jer na pitanje
    „koji je centar najbliži“ kvadrat daje isti odgovor.
    """
    # preko np.newaxis računam razlike za sve parove tačka–centar odjednom, bez petlje
    # (oblik tačke × centri × kolone)
    razlike = X[:, np.newaxis, :] - centri[np.newaxis, :, :]
    # kvadriram razlike i sabiram ih po kolonama, pa mi ostaje jedan broj po paru
    return (razlike ** 2).sum(axis=2)


def izaberi_pocetne_centre(X: np.ndarray, k: int, generator: np.random.Generator) -> np.ndarray:
    """
    Bira k početnih centara postupkom k-means++ i vraća ih kao matricu. Prvi
    centar je nasumična tačka, a svaki sledeći se bira sa verovatnoćom srazmernom
    kvadratu rastojanja do najbližeg već izabranog centra. Tako se centri
    raspoređuju po prostoru i algoritam ređe završi u lošem lokalnom minimumu.
    """
    # prvi centar mi je nasumična tačka iz X, izabrana generatorom sa fiksnim semenom
    centri = [X[generator.integers(len(X))]]

    for _ in range(1, k):
        # za svaku tačku uzimam kvadrat rastojanja do njoj najbližeg od već izabranih centara
        najbliza = rastojanja_do_centara(X, np.array(centri)).min(axis=1)
        zbir = najbliza.sum()
        # kad je zbir nula, nemam po čemu da merim šanse, pa uzimam bilo koju tačku
        if zbir <= 0:                        # svaka tačka već leži na nekom centru
            centri.append(X[generator.integers(len(X))])
            continue
        # dalekoj tački dajem veću šansu; kad podelim zbirom, verovatnoće mi se sabiraju u 1
        verovatnoce = najbliza / zbir
        centri.append(X[generator.choice(len(X), p=verovatnoce)])

    return np.array(centri)


def kmeans_jednom(X: np.ndarray, k: int, najvise_iteracija: int = 300,
                  seme: int = 2026) -> dict:
    """
    Funkcija izvršava jedno pokretanje K-means nad matricom X sa k klastera:
        1) bira početne centre postupkom k-means++,
        2) svaku tačku dodeljuje najbližem centru,
        3) ako se dodela nije promenila, staje,
        4) inače svaki centar pomera u prosek tačaka koje su mu dodeljene i vraća
           se na korak 2, najviše najvise_iteracija puta.
    Vraća rečnik sa oznakama klastera, centrima, inercijom i brojem iteracija.
    """
    # fiksno seme sam stavila da mi isto podešavanje uvek da iste početne centre i klastere
    generator = np.random.default_rng(seme)
    centri = izaberi_pocetne_centre(X, k, generator)
    # oznake punim sa -1 (tačka još nije dodeljena), da prva provera zaustavljanja sigurno ne prođe
    oznake = np.full(len(X), -1)

    # glavnu petlju vrtim dok se dodela ne ustali, a najviše najvise_iteracija puta
    for iteracija in range(1, najvise_iteracija + 1):
        # --- 2) dodela: svakoj tački dajem oznaku centra sa najmanjim rastojanjem (argmin po redu) ---
        rastojanja = rastojanja_do_centara(X, centri)
        nove_oznake = rastojanja.argmin(axis=1)

        # --- 3) ako nijedna tačka nije promenila klaster, prekidam, jer se ni centri ne bi pomerili ---
        if np.array_equal(nove_oznake, oznake):
            break
        oznake = nove_oznake

        # --- 4) pomeranje: svaki centar prebacujem u prosek (težište) tačaka iz njegovog klastera ---
        for redni_broj in range(k):
            pripadnici = X[oznake == redni_broj]
            if len(pripadnici):
                centri[redni_broj] = pripadnici.mean(axis=0)
            else:
                # prazan klaster: centar prebacujem na tačku koja je najdalje od
                # svog najbližeg centra, da klaster ne ostane neiskorišćen
                najgora = rastojanja_do_centara(X, centri).min(axis=1).argmax()
                centri[redni_broj] = X[najgora]

    # inercija mi je zbir kvadrata rastojanja svake tačke do centra njenog klastera
    # (iz matrice rastojanja za svaku tačku uzimam kolonu njene oznake); što je manja,
    # klasteri su zbijeniji. To je isti broj koji na vežbama daje kmeans.inertia_
    inercija = float(rastojanja_do_centara(X, centri)[np.arange(len(X)), oznake].sum())

    # centri koje vraćam su isto što i cluster_centers_ sa vežbi, samo što su
    # u standardizovanim jedinicama sa težinama
    return {"oznake": oznake, "centri": centri, "inercija": inercija,
            "broj_iteracija": iteracija}


def kmeans(X: np.ndarray, k: int, najvise_iteracija: int = 300,
           seme: int = 2026, ispisuj: bool = False, broj_pokretanja: int = 10) -> dict:
    """
    Funkcija pokreće kmeans_jednom broj_pokretanja puta (podrazumevano deset), svaki
    put sa drugim semenom (seme, seme + 1, seme + 2, ...), pa i sa drugim početnim
    centrima, i vraća rešenje sa najmanjom inercijom. Vraća isti rečnik kao
    kmeans_jednom, a broj iteracija u njemu je broj iteracija tog, najboljeg
    pokretanja. Kada je ispisuj uključeno, ispisuje i ishod svakog pokretanja.
    """
    # k-means++ ume da završi u lošem lokalnom minimumu: kod frižidera za K = 4 jedno
    # pokretanje (seme 2026) daje inerciju 364,85, a najbolje od deset 339,72. Zato
    # algoritam pokrećem više puta i zadržavam rešenje sa najmanjom inercijom, kao
    # KMeans(n_init=10) iz biblioteke
    najbolje = None
    for redni_broj in range(broj_pokretanja):
        # svako pokretanje ima svoje fiksno seme, pa i najbolje rešenje ostaje uvek isto
        rezultat = kmeans_jednom(X, k, najvise_iteracija, seme + redni_broj)
        if ispisuj:
            print(f"[INFO] Pokretanje {redni_broj + 1} (seme {seme + redni_broj}): "
                  f"{rezultat['broj_iteracija']} iteracija, inercija {decimalno(rezultat['inercija'], 2)}")
        # pamtim pokretanje sa manjom inercijom; kod jednake inercije ostaje prvo nađeno
        if najbolje is None or rezultat["inercija"] < najbolje["inercija"]:
            najbolje = rezultat
    return najbolje


# ============================================================================
# 3. MERA KVALITETA — Silhouette, ručno
# ============================================================================
def silhouette(X: np.ndarray, oznake: np.ndarray, najvise_uzoraka: int = 2000,
               seme: int = 2026) -> float:
    """
    Računa prosečan Silhouette koeficijent za datu dodelu i vraća broj od −1 do 1.
    Kada tačaka ima više od najvise_uzoraka (2.000), računa ga na nasumičnom uzorku
    te veličine, jer račun raste sa kvadratom broja tačaka.
    Za tačku i:
        a(i) = prosečno rastojanje do ostalih tačaka u njenom klasteru
        b(i) = najmanje prosečno rastojanje do tačaka nekog drugog klastera
        s(i) = (b − a) / max(a, b)
    Blizu 1 znači da je tačka mnogo bliža svom klasteru nego drugom, oko 0 da je
    na granici, a ispod 0 da je verovatno u pogrešnom klasteru.
    """
    # sa jednim klasterom b(i) ne postoji, pa ocenu ne računam i vraćam 0
    if len(set(oznake)) < 2:
        return 0.0

    # račun raste sa kvadratom broja tačaka, pa kad ih ima više od 2.000 uzimam
    # nasumičan uzorak od 2.000; seme je fiksno, da ocena bude ponovljiva
    if len(X) > najvise_uzoraka:
        generator = np.random.default_rng(seme)
        izbor = generator.choice(len(X), najvise_uzoraka, replace=False)
        X, oznake = X[izbor], oznake[izbor]

    # u petlji ispod za svaku tačku računam a(i), b(i) i s(i) i skupljam s(i) u rezultati
    rezultati = []
    for redni_broj in range(len(X)):
        # rastojanja tekuće tačke do svih tačaka računam red po red, a ne celu matricu odjednom,
        # da za 2.000 tačaka ne držim u memoriji sve razlike; koren vadim, jer formula za s(i)
        # radi sa pravim rastojanjima, a ne sa njihovim kvadratima
        rastojanja = np.sqrt(((X - X[redni_broj]) ** 2).sum(axis=1))
        # maska svoj mi označava tačke iz istog klastera kao tekuća tačka
        svoj = oznake == oznake[redni_broj]
        broj_u_svom = svoj.sum()
        if broj_u_svom <= 1:
            rezultati.append(0.0)             # tačka sama u klasteru dobija s = 0
            continue

        # a(i): delim sa (broj − 1), jer je u zbiru i rastojanje tačke do same sebe, koje je 0
        a = rastojanja[svoj].sum() / (broj_u_svom - 1)

        # b(i): za svaki drugi klaster računam prosečno rastojanje i pamtim najmanje od njih
        b = np.inf
        for druga_oznaka in set(oznake):
            if druga_oznaka == oznake[redni_broj]:
                continue
            drugi = oznake == druga_oznaka
            if drugi.any():
                b = min(b, rastojanja[drugi].mean())

        # s(i) = (b − a) / max(a, b); kad su i a i b nula, upisujem 0 da ne delim nulom
        rezultati.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)

    # ukupnu ocenu dobijam kao prosek s(i) po svim tačkama (uzorka)
    return float(np.mean(rezultati))


# ============================================================================
# 4. OPIS KLASTERA
# ============================================================================
def opisi_klastere(zadrzani: pd.DataFrame, oznake: np.ndarray,
                   obelezja: list[str]) -> pd.DataFrame:
    """
    Funkcija grupiše zadržane proizvode po klasteru i za svaki pravi red sa brojem
    i udelom proizvoda, prosečnom cenom i medijanom cene, najčešćom kategorijom i
    brendom, prosekom izabranih obeležja i opisom rečima. Vraća tabelu sortiranu
    po prosečnoj ceni.
    """
    # radim na kopiji, da kolonu klaster ne upišem u samu tabelu zadrzani
    tabela = zadrzani.copy()
    tabela["klaster"] = oznake
    redovi = []

    # za svaki klaster pravim po jedan red: brojeve, cenu, najčešću kategoriju i brend i opis
    for broj_klastera, deo in tabela.groupby("klaster"):
        opis = sastavi_recenicu(deo, tabela, obelezja)
        red = {
            "klaster":              int(broj_klastera),
            "broj_proizvoda":       len(deo),
            "udeo_procenat":        round(100 * len(deo) / len(tabela), 1),
            "prosecna_cena":        round(float(deo["cena_min"].astype(float).mean())),
            "medijana_cene":        round(float(deo["cena_min"].astype(float).median())),
            "najcesca_kategorija":  deo["kategorija"].mode().iloc[0],
            "najcesci_brend":       deo["brend"].mode().iloc[0],
            "opis":                 opis,
        }
        # za svako izabrano obeležje dodajem kolonu prosek_<obeležje>, a None kad vrednosti nema
        for obelezje in obelezja:
            vrednosti = pd.to_numeric(deo[obelezje], errors="coerce")
            red[f"prosek_{obelezje}"] = round(float(vrednosti.mean()), 2) if vrednosti.notna().any() else None
        # rang 3 stare i rang 3 nove skale nisu ista efikasnost, pa uz zajednički
        # prosek dodajem prosek ranga posebno za svaku skalu i udeo stare skale
        if "energetska_rang" in obelezja:
            for skala in ("nova", "stara"):
                rang = pd.to_numeric(deo.loc[deo["energetska_skala"] == skala, "energetska_rang"],
                                     errors="coerce")
                red[f"prosek_rang_{skala}"] = round(float(rang.mean()), 2) if rang.notna().any() else None
            red["udeo_stare_skale"] = round(100 * float((deo["energetska_skala"] == "stara").mean()), 1)
        redovi.append(red)

    # klastere slažem po prosečnoj ceni, od najjeftinijeg ka najskupljem
    return pd.DataFrame(redovi).sort_values("prosecna_cena").reset_index(drop=True)


def sastavi_recenicu(deo: pd.DataFrame, ceo: pd.DataFrame, obelezja: list[str]) -> str:
    """
    Sastavlja kratak opis klastera i vraća ga kao tekst. Prosek cene i svakog
    izabranog obeležja poredi sa prosekom celog skupa i, kad je osetno veći ili
    manji, zapisuje to rečima („skuplji uređaji“, „veća zapremina“).
    """
    # delove opisa skupljam u listu delovi, a na kraju ih spajam zarezom
    delovi = []

    # prosečnu cenu klastera poredim sa prosečnom cenom celog skupa
    cena_klastera = float(deo["cena_min"].astype(float).mean())
    cena_svih = float(ceo["cena_min"].astype(float).mean())
    # za cenu sam uvela dva stepena na svaku stranu (iznad 1,3 proseka „skuplji“, iznad 2
    # „znatno skuplji“), da malo skuplji i mnogo skuplji klaster ne dobiju iste reči
    if cena_klastera > cena_svih * PRAG_CENA_ZNATNO_SKUPLJI:
        delovi.append("znatno skuplji uređaji")
    elif cena_klastera > cena_svih * PRAG_CENA_SKUPLJI:
        delovi.append("skuplji uređaji")
    elif cena_klastera < cena_svih * PRAG_CENA_ZNATNO_JEFTINIJI:
        delovi.append("znatno jeftiniji uređaji")
    elif cena_klastera < cena_svih * PRAG_CENA_JEFTINIJI:
        delovi.append("jeftiniji uređaji")
    else:
        delovi.append("uređaji srednje cene")

    # kategoriju pominjem samo kad skup ima više kategorija i jedna čini preko 60%
    # klastera; kad je klasterovanje već samo nad televizorima, „pretežno televizor“
    # ne govori ništa
    if ceo["kategorija"].nunique() > 1:
        kategorija = deo["kategorija"].mode()
        if len(kategorija):
            udeo = (deo["kategorija"] == kategorija.iloc[0]).mean()
            if udeo > UDEO_PRETEZNE_KATEGORIJE:
                delovi.append(f"pretežno {nazivi.kategorija(kategorija.iloc[0]).lower()}")

    # ostala izabrana obeležja opisujem jedno po jedno, istim poređenjem proseka
    for obelezje in obelezja:
        if obelezje == "cena_min":          # cena je već opisana iznad
            continue
        # obeležje bez ijedne vrednosti ili sa prosekom 0 preskačem, jer odnos proseka
        # tada ne mogu da izračunam
        vrednosti_klastera = pd.to_numeric(deo[obelezje], errors="coerce")
        vrednosti_svih = pd.to_numeric(ceo[obelezje], errors="coerce")
        if not vrednosti_klastera.notna().any() or not vrednosti_svih.notna().any():
            continue
        prosek_klastera, prosek_svih = vrednosti_klastera.mean(), vrednosti_svih.mean()
        if prosek_svih == 0:
            continue
        # kod energetskog ranga manji broj je bolja klasa, a rang 3 stare (A+) i nove (C)
        # skale nije isti nivo. Kad nijedna skala nema bar 80%, pišem „mešane energetske
        # skale“, a inače klaster poredim samo sa uređajima iz iste skale.
        if obelezje == "energetska_rang":
            skale = deo["energetska_skala"].dropna()
            jedna_skala = len(skale) > 0 and skale.value_counts(normalize=True).iloc[0] >= UDEO_JEDNE_SKALE
            if not jedna_skala:
                delovi.append("mešane energetske skale")
                continue
            glavna_skala = skale.value_counts().index[0]
            rang_klastera = pd.to_numeric(
                deo.loc[deo["energetska_skala"] == glavna_skala, obelezje], errors="coerce").mean()
            rang_iste_skale = pd.to_numeric(
                ceo.loc[ceo["energetska_skala"] == glavna_skala, obelezje], errors="coerce").mean()
            if rang_klastera < rang_iste_skale * PRAG_BOLJA_KLASA:
                delovi.append("bolja energetska klasa")
            elif rang_klastera > rang_iste_skale * PRAG_LOSIJA_KLASA:
                delovi.append("lošija energetska klasa")
            continue

        # rod prideva sam vezala za naziv: „veći gabarit“, ali „veća zapremina“
        naziv = OPISNI_NAZIVI.get(obelezje, DOSTUPNA_OBELEZJA.get(obelezje, obelezje).lower())
        muski_rod = naziv.endswith(("gabarit", "kapacitet", "učinak", "nivo buke"))
        # pragove proveravam od najjačeg ka slabijem, pa „znatno“ ima prednost
        if prosek_klastera > prosek_svih * PRAG_ZNATNO_VECI:
            delovi.append(f"znatno {'veći' if muski_rod else 'veća'} {naziv}")
        elif prosek_klastera > prosek_svih * PRAG_VECI:
            delovi.append(f"{'veći' if muski_rod else 'veća'} {naziv}")
        elif prosek_klastera < prosek_svih * PRAG_ZNATNO_MANJI:
            delovi.append(f"znatno {'manji' if muski_rod else 'manja'} {naziv}")
        elif prosek_klastera < prosek_svih * PRAG_MANJI:
            delovi.append(f"{'manji' if muski_rod else 'manja'} {naziv}")

    # opis skraćujem na najviše četiri dela, a najčešću energetsku klasu dodajem tek
    # posle toga, da ne otpadne kad je izabrano mnogo obeležja
    delovi = delovi[:NAJVISE_DELOVA_OPISA]

    # kad klasu ima više od pola klastera, navodim najčešću klasu zajedno sa skalom,
    # jer „A“ nove i „A“ stare skale nije isto; zato brojim parove (klasa, skala),
    # da mi se te dve oznake ne saberu
    sa_klasom = deo.dropna(subset=["energetska_klasa"])
    if len(sa_klasom) > len(deo) * UDEO_SA_ENERGETSKOM_KLASOM:
        parovi = sa_klasom.groupby(["energetska_klasa", "energetska_skala"], dropna=False).size()
        klasa, skala = parovi.idxmax()
        oznaka_skale = {"stara": " po prethodnoj klasifikaciji", "nova": " po novoj skali"}.get(skala, "")
        delovi.append(f"najčešće energetska klasa {klasa}{oznaka_skale}")

    return ", ".join(delovi)


# ============================================================================
# 5. GRAFIKONI
# ============================================================================
def nacrtaj_lakat(X: np.ndarray, najveci_k: int = 10, naslov_dodatak: str = "") -> None:
    """
    Pokreće K-means za K od 2 do najveci_k, beleži inerciju i Silhouette i crta
    ih na grafikonu metode lakta. Iste brojeve snima i u kmeans_lakat.csv, da se
    izbor K obrazloži brojevima, a ne samo pogledom na grafikon.
    """
    # pravim foldere za grafikone i modele ako još ne postoje
    FOLDER_GRAFIKONA.mkdir(parents=True, exist_ok=True)
    FOLDER_MODELA.mkdir(parents=True, exist_ok=True)
    inercije, silhouete, vrednosti_k = [], [], list(range(2, najveci_k + 1))

    # ova petlja mi je kao ona sa vežbi, gde se za svako K pravi KMeans i
    # pamti kmeans.inertia_; ja pozivam svoj kmeans() za K od 2 do najveci_k i uz
    # inerciju pamtim i Silhouette
    for k in vrednosti_k:
        rezultat = kmeans(X, k)
        inercije.append(rezultat["inercija"])
        silhouete.append(silhouette(X, rezultat["oznake"]))
        print(f"[INFO] K={k:>2}   inercija={decimalno(rezultat['inercija'], 1):>12}   "
              f"silhouette={decimalno(silhouete[-1], 3)}")

    # iste brojeve, zaokružene, snimam u kmeans_lakat.csv
    pd.DataFrame({"k": vrednosti_k, "inercija": np.round(inercije, 2),
                  "silhouette": np.round(silhouete, 4)}).to_csv(
        FOLDER_MODELA / "kmeans_lakat.csv", index=False, encoding="utf-8")
    print("[OK] kmeans_lakat.csv")

    # grafikon inercije po K je metod lakta sa vežbi; inerciju sam stavila na
    # levu osu (bordo), a Silhouette na desnu (oker), koju mi twinx() pravi nad istom x osom;
    # natpis i brojevi svake ose su u boji njene linije, a za oker tekst uzimam tamniji ton
    figura, leva = plt.subplots(figsize=(10, 6))
    leva.plot(vrednosti_k, inercije, "o-", color=BORDO, linewidth=2, markersize=7, label="inercija")
    leva.set_xlabel("Broj klastera K")
    leva.set_ylabel("Inercija (zbir kvadrata rastojanja)", color=BORDO)
    leva.tick_params(axis="y", labelcolor=BORDO)

    desna = leva.twinx()
    desna.plot(vrednosti_k, silhouete, "s--", color=OKER, linewidth=2, markersize=7,
               markeredgecolor=TAMNI_OKER, label="Silhouette")
    desna.set_ylabel("Silhouette koeficijent", color=TAMNI_OKER)
    desna.tick_params(axis="y", labelcolor=TAMNI_OKER)
    # na desnoj osi pišem decimalni zarez umesto tačke
    desna.yaxis.set_major_formatter(FuncFormatter(lambda vrednost, _: f"{vrednost:.3f}".replace(".", ",")))

    # dodajem naslov i blagu mrežu, snimam sliku i zatvaram figuru
    leva.set_title(f"Izbor broja klastera{naslov_dodatak}: metoda lakta i Silhouette koeficijent")
    leva.grid(alpha=0.25)
    figura.savefig(FOLDER_GRAFIKONA / "10_kmeans_lakat.png")
    plt.close(figura)
    print("[OK] 10_kmeans_lakat.png")


def nacrtaj_rasipanje(zadrzani: pd.DataFrame, oznake: np.ndarray,
                      obelezja: list[str], naslov_dodatak: str = "") -> None:
    """
    Crta dijagram rasipanja za prva dva izabrana obeležja, u originalnim jedinicama,
    sa tačkama obojenim po klasteru. Ako je izabrano samo jedno obeležje, ne crta ništa.
    """
    # za dijagram rasipanja mi trebaju bar dva obeležja, pa sa jednim samo izlazim
    if len(obelezja) < 2:
        return
    prva, druga = obelezja[0], obelezja[1]
    # ose crtam u originalnim jedinicama iz zadrzani, a ne iz standardizovane matrice,
    # da se cena i ostale vrednosti čitaju normalno
    x = pd.to_numeric(zadrzani[prva], errors="coerce")
    y = pd.to_numeric(zadrzani[druga], errors="coerce")

    figura, osa = plt.subplots(figsize=(10, 7))
    # svaki klaster crtam posebnim scatter pozivom u svojoj boji, kao bojenje tačaka po
    # klasi na vežbama
    for broj_klastera in sorted(set(oznake)):
        maska = oznake == broj_klastera
        osa.scatter(x[maska], y[maska], s=22, alpha=0.65,
                    color=BOJE[broj_klastera % len(BOJE)],
                    label=f"Klaster {broj_klastera} (n = {maska.sum():,})".replace(",", "."),
                    edgecolor="none")
    # nazive osa uzimam iz DOSTUPNA_OBELEZJA, a uz cenu dopisujem RSD
    osa.set_xlabel(DOSTUPNA_OBELEZJA.get(prva, prva) + (" (RSD)" if prva == "cena_min" else ""))
    osa.set_ylabel(DOSTUPNA_OBELEZJA.get(druga, druga) + (" (RSD)" if druga == "cena_min" else ""))
    # brojeve na osama pišem sa tačkom za hiljade (1.000 umesto 1,000)
    hiljade = FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", "."))
    osa.xaxis.set_major_formatter(hiljade)
    osa.yaxis.set_major_formatter(hiljade)
    osa.set_title(f"Klasteri proizvoda{naslov_dodatak}")
    osa.legend(frameon=False)
    osa.grid(alpha=0.2)
    osa.spines[["top", "right"]].set_visible(False)
    figura.savefig(FOLDER_GRAFIKONA / "11_kmeans_rasipanje.png")
    plt.close(figura)
    print("[OK] 11_kmeans_rasipanje.png")


def nacrtaj_velicine(opis: pd.DataFrame) -> None:
    """
    Crta dva stubičasta dijagrama, broj proizvoda (sa udelom) i prosečnu cenu po
    klasteru, i snima ih u 12_kmeans_velicine.png.
    """
    # levo crtam broj proizvoda, a desno prosečnu cenu; boja stubića je ista kao boja
    # tog klastera na dijagramu rasipanja. Slika sa dva dela se u izveštaju smanji na širinu
    # strane, pa joj dajem užu figuru i veća slova, da se brojevi čitaju i posle smanjenja.
    figura, (leva, desna) = plt.subplots(1, 2, figsize=(11, 5.2))
    oznake = [f"Klaster {int(r)}" for r in opis["klaster"]]
    boje = [BOJE[int(r) % len(BOJE)] for r in opis["klaster"]]
    slova = 13

    leva.bar(oznake, opis["broj_proizvoda"], color=boje, edgecolor=TAMNI_BORDO, linewidth=0.8)
    leva.set_title("Broj proizvoda po klasteru")
    leva.set_ylabel("Broj proizvoda")
    # iznad svakog stubića ispisujem broj proizvoda i udeo sa decimalnim zarezom
    for pravougaonik, broj, udeo in zip(leva.patches, opis["broj_proizvoda"], opis["udeo_procenat"]):
        leva.text(pravougaonik.get_x() + pravougaonik.get_width() / 2,
                  pravougaonik.get_height() * 1.01, f"{broj}\n" + f"{udeo:.1f}".replace(".", ",") + "%",
                  ha="center", va="bottom", fontsize=slova)
    # gornju granicu ose podižem za 18%, da natpisi iznad stubića stanu
    leva.set_ylim(0, opis["broj_proizvoda"].max() * 1.18)
    leva.spines[["top", "right"]].set_visible(False)

    desna.bar(oznake, opis["prosecna_cena"], color=boje, edgecolor=TAMNI_BORDO, linewidth=0.8)
    desna.set_title("Prosečna cena po klasteru")
    desna.set_ylabel("Prosečna cena (RSD)")
    # iznad desnih stubića pišem prosečnu cenu sa tačkom za hiljade
    for pravougaonik, cena in zip(desna.patches, opis["prosecna_cena"]):
        desna.text(pravougaonik.get_x() + pravougaonik.get_width() / 2,
                   pravougaonik.get_height() * 1.01,
                   f"{int(cena):,}".replace(",", "."), ha="center", va="bottom", fontsize=slova)
    desna.set_ylim(0, opis["prosecna_cena"].max() * 1.18)
    desna.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", ".")))
    desna.spines[["top", "right"]].set_visible(False)

    # na oba dela povećavam naslov, natpise osa i brojeve na osama
    for osa in (leva, desna):
        osa.title.set_fontsize(slova + 3)
        osa.xaxis.label.set_size(slova + 1)
        osa.yaxis.label.set_size(slova + 1)
        osa.tick_params(labelsize=slova)

    figura.savefig(FOLDER_GRAFIKONA / "12_kmeans_velicine.png")
    plt.close(figura)
    print("[OK] 12_kmeans_velicine.png")


# ============================================================================
# Glavni program
# ============================================================================
def main() -> None:
    """
    Čita opcije iz komandne linije, priprema matricu i zatim crta metodu lakta ili
    radi jedno klasterovanje, ispisuje opis klastera i snima rezultate.
    """
    # opcije komandne linije: K, kategorija, obeležja, težine i --lakat
    parser = argparse.ArgumentParser(description="Klasterovanje proizvoda algoritmom K-means.")
    parser.add_argument("--k", type=int, default=4, help="broj klastera")
    parser.add_argument("--kategorija", default=None, help="ograničiti na jednu kategoriju")
    parser.add_argument("--obelezja", default="cena_min,gabarit_cm3,energetska_rang",
                        help="spisak obeležja razdvojen zarezom")
    parser.add_argument("--tezine", default=None,
                        help="težine u procentima, razdvojene zarezom (npr. 50,30,20)")
    parser.add_argument("--lakat", action="store_true",
                        help="nacrtati metodu lakta umesto jednog klasterovanja")
    argumenti = parser.parse_args()

    # nazive obeležja proveravam pre učitavanja baze, da mi se greška u nazivu javi odmah
    obelezja = [o.strip() for o in argumenti.obelezja.split(",") if o.strip()]
    nepoznata = [o for o in obelezja if o not in DOSTUPNA_OBELEZJA]
    if nepoznata:
        print(f"[GRESKA] Nepoznata obeležja: {', '.join(nepoznata)}")
        print(f"[INFO] Dostupna: {', '.join(DOSTUPNA_OBELEZJA)}")
        return

    # težine iz --tezine pretvaram u brojeve; bez te opcije svako obeležje dobija 100 / broj obeležja
    if argumenti.tezine:
        tezine = [float(t) for t in argumenti.tezine.split(",")]
    else:
        tezine = [100 / len(obelezja)] * len(obelezja)      # svima isti udeo

    # učitavam prečišćene proizvode i, ako je zadata kategorija, zadržavam samo nju
    tabela = ucitaj_preciscene()
    if argumenti.kategorija:
        tabela = tabela[tabela["kategorija"] == argumenti.kategorija].reset_index(drop=True)
        print(f"[INFO] Kategorija '{argumenti.kategorija}': {decimalno(len(tabela), 0)} proizvoda")

    # ovde dobijam matricu X za algoritam i tabelu proizvoda koji su ostali posle izbacivanja
    X, zadrzani = pripremi_matricu(tabela, obelezja, tezine)
    print(f"[INFO] Za klasterovanje ostalo {decimalno(len(zadrzani), 0)} proizvoda sa svim "
          f"izabranim karakteristikama ({len(obelezja)} obeležja)")

    # naziv kategorije dopisujem u naslove grafikona, kad je kategorija zadata
    dodatak = f" — {nazivi.kategorija(argumenti.kategorija)}" if argumenti.kategorija else ""
    # sa --lakat samo crtam metodu lakta i ne radim jedno klasterovanje
    if argumenti.lakat:
        nacrtaj_lakat(X, naslov_dodatak=dodatak)
        return

    # klasterujem sa zadatim K (najbolje od deset pokretanja) i ocenjujem Silhouette koeficijentom
    rezultat = kmeans(X, argumenti.k, ispisuj=True)
    ocena = silhouette(X, rezultat["oznake"])
    print(f"[OK] K={argumenti.k}, najbolje pokretanje: {rezultat['broj_iteracija']} iteracija, "
          f"inercija={decimalno(rezultat['inercija'], 1)}, Silhouette={decimalno(ocena, 3)}")

    # opis klastera ispisujem u konzoli, klaster po klaster
    opis = opisi_klastere(zadrzani, rezultat["oznake"], obelezja)
    print("\n[INFO] Opis klastera:")
    for _, red in opis.iterrows():
        # cenu i udeo formatiram posebno, jer bi .replace(",", ".") nad celim redom
        # promenio i zarez koji stoji posle zagrade u rečenici
        cena = f"{red['prosecna_cena']:,.0f}".replace(",", ".")
        udeo = f"{red['udeo_procenat']:.1f}".replace(".", ",")
        print(f"   Klaster {red['klaster']}: {red['broj_proizvoda']:>4} proizvoda "
              f"({udeo}%), prosečna cena {cena:>9} RSD")
        print(f"      → {red['opis']}")

    # za kmeans_rezultat.csv pravim kopiju tabele i dopisujem joj kolonu klaster
    FOLDER_MODELA.mkdir(parents=True, exist_ok=True)
    zadrzani_sa_klasterom = zadrzani.copy()
    zadrzani_sa_klasterom["klaster"] = rezultat["oznake"]
    # uz pripadnost klasteru snimam i energetsku klasu i skalu, da se vidi koliko
    # uređaja u kom klasteru je sa stare, a koliko sa nove skale
    kolone = ["id", "brend", "naziv", "kategorija", "cena_min", *obelezja,
              "energetska_klasa", "energetska_skala", "klaster"]
    # preko dict.fromkeys izbacujem ponovljene kolone (cena_min može biti i među
    # obeležjima), a redosled mi ostaje; zadržavam samo kolone koje tabela zaista ima
    kolone = list(dict.fromkeys(k for k in kolone if k in zadrzani_sa_klasterom.columns))
    zadrzani_sa_klasterom[kolone].to_csv(
        FOLDER_MODELA / "kmeans_rezultat.csv", index=False, encoding="utf-8")
    opis.to_csv(FOLDER_MODELA / "kmeans_opis.csv", index=False, encoding="utf-8")
    # podešavanje, inerciju i Silhouette snimam u kmeans_ocena.csv, da izveštaj ne zavisi
    # od ispisa u konzoli
    pd.DataFrame([{
        "kategorija": argumenti.kategorija or "sve", "k": argumenti.k,
        "obelezja": ",".join(obelezja), "tezine": ",".join(f"{t:g}" for t in tezine),
        "broj_proizvoda": len(zadrzani), "broj_iteracija": rezultat["broj_iteracija"],
        "inercija": round(rezultat["inercija"], 2), "silhouette": round(ocena, 4),
    }]).to_csv(FOLDER_MODELA / "kmeans_ocena.csv", index=False, encoding="utf-8")

    # na kraju crtam dijagram rasipanja i veličine klastera
    nacrtaj_rasipanje(zadrzani, rezultat["oznake"], obelezja, dodatak)
    nacrtaj_velicine(opis)
    print(f"[OK] Rezultati snimljeni u {FOLDER_MODELA}")


if __name__ == "__main__":
    main()
