#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grafikoni.py — Vizuelizacija podataka iz prečišćene baze (Zadatak 3).

Opis:
Skripta čita podatke iz prečišćene baze, crta četiri grafikona iz Zadatka 3,
svaki sa naslovom, i snima ih kao slike. Uz stubiće piše i broj i procenat,
jer zadatak traži „broj i procentualni odnos“. Energetska klasa se
crta posebno za novu i posebno za staru skalu, jer klasa A na te dve skale nije
isti nivo efikasnosti.

Grafikoni:
    1. 10 najzastupljenijih kategorija proizvoda
    2. 10 najzastupljenijih brendova
    3. Raspodela proizvoda po cenovnim opsezima (stubići i pita)
    4. Raspodela proizvoda po energetskoj klasi, nova i stara skala odvojeno
    (grafikone 07–09 crta models/regresija.py, a 10–12 models/kmeans.py)

Ulazi:
    baza psz_preciscena, tabela preciscena.proizvodi

Izlazi:
    izvestaj/grafikoni/01_kategorije.png ... 04_energetska_klasa.png

Primer poziva:
    python grafikoni.py
    python grafikoni.py --format jpg
    python grafikoni.py --izlaz neki_folder
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                       # crtam direktno u fajl, bez otvaranja prozora
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd

# dodajem folder kod u putanju, da bih videla paket zajednicko (veza sa bazom, nazivi, putanje)
sys.path.append(str(Path(__file__).resolve().parents[1]))
from zajednicko.baza import veza
from zajednicko import nazivi
from zajednicko.putanje import FOLDER_GRAFIKONA

# -------------------------------
# Izgled grafikona
# -------------------------------
# za sve grafikone sam izabrala bordo paletu, istu kao u aplikaciji; oker mi je boja za naglasak
BORDO = "#7A1F3D"
TAMNI_BORDO = "#4E1226"
SVETLI_BORDO = "#B23A5B"
RUZ = "#D98BA0"
OKER = "#C47A93"
POZADINA = "#FBF4F6"            # svetla, skoro bela ružičasta podloga
TEKST = "#2B2024"               # skoro crna, da se tekst čita i kad se slika smanji
PRIGUSENO = "#6B4F59"           # za napomene u uglu slike
IVICA = "#8C6A76"               # ose i crtice na osama
MREZA = "#C9A3B0"               # mreža, uz providnost iz poziva grid()

# svim grafikonima dajem isti font, veličine slova i boje; "tight" pri snimanju mi seče prazne ivice
plt.rcParams.update({
    "font.family":      "Times New Roman",
    "axes.titlesize":   15,
    "axes.titleweight": "bold",
    "axes.titlecolor":  TAMNI_BORDO,
    "axes.titlepad":    10,
    "axes.labelsize":   13,
    "axes.labelcolor":  TEKST,
    "axes.edgecolor":   IVICA,
    "axes.facecolor":   POZADINA,
    "figure.facecolor": POZADINA,
    "text.color":       TEKST,
    "xtick.color":      IVICA,
    "ytick.color":      IVICA,
    "xtick.labelcolor": TEKST,
    "ytick.labelcolor": TEKST,
    "xtick.labelsize":  12,
    "ytick.labelsize":  12,
    "legend.fontsize":  12,
    "grid.color":       MREZA,
    "legend.edgecolor": MREZA,
    "figure.dpi":       120,
    "savefig.bbox":     "tight",
})

# ovaj formater mi piše brojeve na osama sa tačkom za hiljade (1.750, 25.000), kako se piše na srpskom
HILJADE = FuncFormatter(lambda vrednost, _: f"{vrednost:,.0f}".replace(",", "."))

# Grafikoni 3 i 4 imaju po dva dela u jednoj slici, a u izveštaju stoje na istoj širini strane
# kao jednodelni, pa se slika tamo smanji skoro dvaput. Zato im dajem veća slova i ne širim ih,
# da se brojevi uz stubiće čitaju i posle smanjenja.
DVODELNI_SIRINA = (11, 5.2)
DVODELNI_SLOVA = 14

# cenovni opsezi imaju redosled, pa ih bojim od svetlog ka tamnom bordou: što skuplje, to tamnije
BOJE_OPSEGA = [RUZ, SVETLI_BORDO, BORDO, TAMNI_BORDO]

# Cenovni opsezi iz zadatka: (naziv, donja, gornja, uključena donja, uključena gornja).
# Po tekstu zadatka tačno 300.000 upada u treći i u četvrti opseg, pa sam ga stavila
# samo u „300.000 i više“, da se ne broji dvaput. Granice sam nadovezala bez rupa.
CENOVNI_OPSEZI = [
    ("do 30.000",          float("-inf"), 30_000,        False, True),    # cena ≤ 30.000
    ("30.001 - 100.000",   30_000,        100_000,       False, True),    # 30.000 < cena ≤ 100.000
    ("100.001 - 300.000",  100_000,       300_000,       False, False),   # 100.000 < cena < 300.000
    ("300.000 i više",     300_000,       float("inf"),  True,  True),    # cena ≥ 300.000
]


# -------------------------------
# Pomoćne funkcije
# -------------------------------
def lepo(kategorija: str) -> str:
    """Vraća čitljiv naziv kategorije za prikaz (iz zajedničkog rečnika)."""
    # u bazi piše npr. 'frizider', a na grafikonu hoću lep naziv, pa ga uzimam iz rečnika
    return nazivi.kategorija(kategorija)


def upit(sql: str) -> pd.DataFrame:
    """Izvršava SQL upit nad bazom psz_preciscena i vraća rezultat kao pandas tabelu."""
    # otvaram vezu, izvršim upit kurzorom i od redova i naziva kolona iz description
    # složim DataFrame, sa kojim mi je posle lakše da crtam
    with veza("preciscena") as konekcija:
        with konekcija.cursor() as kurzor:
            kurzor.execute(sql)
            kolone = [opis[0] for opis in kurzor.description]
            return pd.DataFrame(kurzor.fetchall(), columns=kolone)


def snimi(figura, naziv: str, izlaz: Path, format_slike: str) -> None:
    """
    Pravi izlazni folder ako ga nema, snima figuru pod zadatim nazivom i
    formatom i zatvara je, da ne ostaje u memoriji.
    """
    # sve grafikone snimam kroz ovu jednu funkciju, pa naziv fajla i format biram na jednom mestu
    izlaz.mkdir(parents=True, exist_ok=True)
    putanja = izlaz / f"{naziv}.{format_slike}"
    figura.savefig(putanja)
    plt.close(figura)
    print(f"[OK] {putanja.name}")


def uvecaj_slova(osa, slova: int) -> None:
    """Postavlja veličinu slova naslova, natpisa osa i brojeva na osama jednog dela slike."""
    # naslov dela ostavljam malo veći od ostalog teksta, kao i na jednodelnim grafikonima
    osa.title.set_fontsize(slova + 2)
    osa.xaxis.label.set_size(slova)
    osa.yaxis.label.set_size(slova)
    osa.tick_params(labelsize=slova)


def oznaci_stubice(osa, vrednosti, procenti, vodoravno: bool = False,
                   slova: int = 11) -> None:
    """
    Uz svaki stubić ispisuje broj i procenat: iznad stubića u dva reda, a kod
    vodoravnog grafikona desno od stubića, u jednom redu.
    """
    # osa.patches su mi već nacrtani stubići, pa ih uparujem sa brojem i procentom istim redom
    for pravougaonik, broj, procenat in zip(osa.patches, vrednosti, procenti):
        # broj pišem sa tačkom za hiljade, a procenat sa decimalnim zarezom
        oznaka = f"{broj:,}".replace(",", ".") + "\n" + f"{procenat:.1f}".replace(".", ",") + "%"
        if vodoravno:
            # kod barh tekst ide malo desno od kraja stubića, na sredini njegove visine
            osa.text(pravougaonik.get_width() * 1.01,
                     pravougaonik.get_y() + pravougaonik.get_height() / 2,
                     oznaka.replace("\n", "  "), va="center", fontsize=slova)
        else:
            # kod uspravnog stubića tekst centriram iznad vrha
            osa.text(pravougaonik.get_x() + pravougaonik.get_width() / 2,
                     pravougaonik.get_height() * 1.01, oznaka,
                     ha="center", va="bottom", fontsize=slova)


# -------------------------------
# Grafikon 1: kategorije
# -------------------------------
def grafikon_kategorije(izlaz: Path, format_slike: str) -> None:
    """
    Broji proizvode po kategoriji, crta 10 najbrojnijih kategorija sa brojem i
    procentom i snima grafikon kao 01_kategorije.
    """
    # brojanje po kategoriji prepuštam bazi, a u Python dobijam samo deset redova
    podaci = upit("""
        SELECT  kategorija, COUNT(*) AS broj
        FROM        preciscena.proizvodi
        GROUP BY    kategorija
        ORDER BY    broj DESC, kategorija
        LIMIT       10
    """)
    # procenat računam od svih proizvoda u bazi, a ne samo od prvih deset
    ukupno = upit("SELECT COUNT(*) AS n FROM preciscena.proizvodi")["n"].iloc[0]
    podaci["procenat"] = podaci["broj"] / ukupno * 100
    podaci["naziv"] = podaci["kategorija"].map(lepo)

    # uspravne stubiće crtam sa osa.bar; svi su iste bordo boje, jer razliku već pokazuje visina
    figura, osa = plt.subplots(figsize=(11, 6))
    osa.bar(podaci["naziv"], podaci["broj"], color=BORDO)
    osa.set_title("Deset najzastupljenijih kategorija proizvoda bele tehnike")
    osa.set_ylabel("Broj proizvoda")
    # osu Y podižem za 18% iznad najvećeg stubića, da oznaka u dva reda stane iznad njega
    osa.set_ylim(0, podaci["broj"].max() * 1.18)
    osa.yaxis.set_major_formatter(HILJADE)
    plt.xticks(rotation=30, ha="right")
    oznaci_stubice(osa, podaci["broj"], podaci["procenat"])
    osa.spines[["top", "right"]].set_visible(False)
    # u donji desni ugao upisujem ukupan broj, da se vidi od čega su procenti
    figura.text(0.99, 0.01, f"Ukupno u bazi: {ukupno:,}".replace(",", "."),
                ha="right", fontsize=11, color=PRIGUSENO)
    snimi(figura, "01_kategorije", izlaz, format_slike)


# -------------------------------
# Grafikon 2: brendovi
# -------------------------------
def grafikon_brendovi(izlaz: Path, format_slike: str) -> None:
    """
    Crta vodoravni grafikon 10 brendova sa najviše proizvoda, uz broj i procenat
    od cele baze, i snima ga kao 02_brendovi.
    """
    # isti postupak kao za kategorije, samo grupišem po koloni brend
    podaci = upit("""
        SELECT  brend, COUNT(*) AS broj
        FROM        preciscena.proizvodi
        GROUP BY    brend
        ORDER BY    broj DESC, brend
        LIMIT       10
    """)
    ukupno = upit("SELECT COUNT(*) AS n FROM preciscena.proizvodi")["n"].iloc[0]
    podaci["procenat"] = podaci["broj"] / ukupno * 100
    podaci = podaci.iloc[::-1]              # barh crta prvi red na dnu, pa obrćem da najveći bude na vrhu

    # za brendove sam izabrala vodoravne stubiće, jer se imena brendova tako lakše čitaju
    figura, osa = plt.subplots(figsize=(10, 6.5))
    osa.barh(podaci["brend"], podaci["broj"], color=BORDO)
    osa.set_title("Deset najzastupljenijih brendova po broju artikala")
    osa.set_xlabel("Broj proizvoda")
    osa.set_xlim(0, podaci["broj"].max() * 1.22)
    osa.xaxis.set_major_formatter(HILJADE)
    oznaci_stubice(osa, podaci["broj"], podaci["procenat"], vodoravno=True)
    osa.spines[["top", "right"]].set_visible(False)
    figura.text(0.99, 0.01, f"Ukupno u bazi: {ukupno:,}".replace(",", "."),
                ha="right", fontsize=11, color=PRIGUSENO)
    snimi(figura, "02_brendovi", izlaz, format_slike)


# -------------------------------
# Grafikon 3: cenovni opsezi
# -------------------------------
def grafikon_cenovni_opsezi(izlaz: Path, format_slike: str) -> None:
    """
    Raspoređuje cene u četiri opsega iz CENOVNI_OPSEZI i crta ih dvaput: levo
    stubiće sa brojem i procentom, desno pitu sa procentualnim odnosom.
    Snima grafikon kao 03_cenovni_opsezi.
    """
    # ovde mi iz baze trebaju samo cene, a u opsege ih delim sama u Python-u
    podaci = upit("SELECT cena_min FROM preciscena.proizvodi WHERE cena_min IS NOT NULL")
    cene = podaci["cena_min"].astype(float)

    # za svaki opseg brojim cene između granica, sa < ili ≤ kako piše u CENOVNI_OPSEZI
    brojevi = []
    for _, donja, gornja, ukljucena_donja, ukljucena_gornja in CENOVNI_OPSEZI:
        iznad_donje = (cene >= donja) if ukljucena_donja else (cene > donja)
        ispod_gornje = (cene <= gornja) if ukljucena_gornja else (cene < gornja)
        brojevi.append(int((iznad_donje & ispod_gornje).sum()))
    oznake_opsega = [oznaka for oznaka, _, _, _, _ in CENOVNI_OPSEZI]

    # provera: zbir po opsezima mora biti jednak broju cena, inače opsezi imaju rupu ili preklop
    if sum(brojevi) != len(cene):
        raise ValueError(f"Opsezi ne pokrivaju sve cene: {sum(brojevi)} od {len(cene)}")
    ukupno = sum(brojevi)
    procenti = [b / ukupno * 100 for b in brojevi]

    # jedna slika sa dva dela: leva osa za stubiće, desna za pitu
    figura, (leva, desna) = plt.subplots(1, 2, figsize=DVODELNI_SIRINA)

    # levo idu stubići za četiri opsega, od svetlog ka tamnom bordou; tanka tamna ivica mi
    # ocrtava i najsvetliji stubić, da se ne izgubi na svetloj podlozi
    leva.bar(oznake_opsega, brojevi, color=BOJE_OPSEGA, edgecolor=TAMNI_BORDO, linewidth=0.8)
    leva.set_title("Broj proizvoda po cenovnim opsezima")
    leva.set_ylabel("Broj proizvoda")
    leva.set_xlabel("Cenovni opseg (RSD)")
    leva.set_ylim(0, max(brojevi) * 1.18)
    leva.yaxis.set_major_formatter(HILJADE)
    oznaci_stubice(leva, brojevi, procenti, slova=DVODELNI_SLOVA)
    leva.spines[["top", "right"]].set_visible(False)
    plt.setp(leva.get_xticklabels(), rotation=15, ha="right")
    uvecaj_slova(leva, DVODELNI_SLOVA)

    # u isečak ispod 5% procenat ne staje, pa ga pišem uz naziv opsega, van kruga;
    # autopct za takve isečke vraća prazan tekst, da se procenat ne ispiše dvaput
    oznake_pite = [f"{oznaka} (" + f"{procenat:.1f}".replace(".", ",") + "%)" if procenat < 5 else oznaka
                   for oznaka, procenat in zip(oznake_opsega, procenti)]
    # pitu počinjem od vrha (90°) i idem u smeru kazaljke, istim redom kao stubići levo
    _, _, procenti_u_krugu = desna.pie(
        brojevi, labels=oznake_pite, colors=BOJE_OPSEGA,
        autopct=lambda udeo: (f"{udeo:.1f}".replace(".", ",") + "%") if udeo >= 5 else "",
        startangle=90, counterclock=False,
        textprops={"fontsize": DVODELNI_SLOVA},
        wedgeprops={"edgecolor": POZADINA, "linewidth": 2})
    # na tamnim isečcima procenat pišem belim slovima, a na svetlom ružu tamnim
    for tekst, boja in zip(procenti_u_krugu, BOJE_OPSEGA):
        tekst.set_color(TEKST if boja == RUZ else "white")
    desna.set_title("Procentualni odnos po cenovnim opsezima")
    uvecaj_slova(desna, DVODELNI_SLOVA)

    # glavni naslov malo podižem (y=1.03), da ne dodiruje naslove dva dela
    figura.suptitle("Raspodela proizvoda bele tehnike po ceni", fontsize=DVODELNI_SLOVA + 3,
                    fontweight="bold", color=TAMNI_BORDO, y=1.03)
    snimi(figura, "03_cenovni_opsezi", izlaz, format_slike)


# -------------------------------
# Grafikon 4: energetska klasa
# -------------------------------
def grafikon_energetska_klasa(izlaz: Path, format_slike: str) -> None:
    """
    Broji proizvode po energetskoj klasi i crta levo novu, a desno staru skalu.
    Klase su poređane po rangu unutar svoje skale, a oba dela imaju istu osu Y, pa se
    visine stubića mogu uporediti. Snima grafikon kao 04_energetska_klasa.
    """
    # grupišem i po energetska_klasa_num, da bih mogla da ređam klase po rangu, a ne po abecedi
    podaci = upit("""
        SELECT  energetska_skala, energetska_klasa, COUNT(*) AS broj
        FROM        preciscena.proizvodi
        WHERE       energetska_klasa IS NOT NULL
          AND       energetska_skala IN ('nova', 'stara')
        GROUP BY    energetska_skala, energetska_klasa, energetska_klasa_num
        ORDER BY    energetska_skala, energetska_klasa_num
    """)
    # ako nijedan proizvod nema klasu, ne pravim praznu sliku nego samo javim i izađem
    if podaci.empty:
        print("[INFO] Nema podataka o energetskoj klasi — grafikon 4 se preskače")
        return

    # ukupno su proizvodi sa poznatom klasom i skalom, pa se procenti sa oba dela slažu
    ukupno = int(podaci["broj"].sum())
    figura, ose = plt.subplots(1, 2, figsize=DVODELNI_SIRINA)
    # granicu ose Y računam iz najvećeg stubića cele slike, da oba dela imaju istu podelu i
    # da se visine stubića mogu uporediti; da svaki deo ima svoju osu, stubić sa manjim
    # brojem izgledao bi viši od stubića sa većim
    granica_ose = podaci["broj"].max() * 1.18

    # svaka skala dobija svoj deo grafikona i svoju boju (nova bordo, stara oker), da se odmah
    # vidi da su to dve različite skale; ako skala nema podataka, deo sakrivam
    for osa, skala, boja in zip(ose, ["nova", "stara"], [BORDO, OKER]):
        deo = podaci[podaci["energetska_skala"] == skala]
        if deo.empty:
            osa.set_visible(False)
            continue
        procenti = deo["broj"] / ukupno * 100
        osa.bar(deo["energetska_klasa"], deo["broj"], color=boja, edgecolor=TAMNI_BORDO, linewidth=0.8)
        # naslov dela biram prema skali, da se odmah vidi koja su slova u pitanju
        naslov = ("Nova skala (A–G, od 2021.)" if skala == "nova"
                  else "Prethodna klasifikacija (A+++ i niže)")
        osa.set_title(naslov)
        osa.set_xlabel("Energetska klasa")
        osa.set_ylabel("Broj proizvoda")
        osa.set_ylim(0, granica_ose)
        osa.yaxis.set_major_formatter(HILJADE)
        # stara skala ima osam uskih stubića, pa oznake pišem za nijansu manjim slovima,
        # da se procenti susednih stubića ne dodiruju
        oznaci_stubice(osa, deo["broj"].tolist(), procenti.tolist(), slova=DVODELNI_SLOVA - 2)
        osa.spines[["top", "right"]].set_visible(False)
        uvecaj_slova(osa, DVODELNI_SLOVA)

    # naslov u dva reda podižem (y=1.06), da se ne preklopi sa naslovima dva dela
    figura.suptitle("Raspodela proizvoda po energetskoj klasi\n"
                    "(slova skala nisu uporediva, pa se prikazuju odvojeno; osa Y je ista na oba dela)",
                    fontsize=DVODELNI_SLOVA + 3, fontweight="bold", color=TAMNI_BORDO, y=1.06)
    # procenti na oba dela su od istog ukupnog broja, pa u napomeni navodim i udeo svake skale
    udeo_nove = 100 * podaci.loc[podaci["energetska_skala"] == "nova", "broj"].sum() / ukupno
    napomena = (f"Procenti su od svih {ukupno:,} proizvoda sa poznatom klasom i skalom".replace(",", ".")
                + " (nova skala " + f"{udeo_nove:.1f}".replace(".", ",") + "%, prethodna "
                + f"{100 - udeo_nove:.1f}".replace(".", ",") + "%)")
    figura.text(0.99, -0.01, napomena, ha="right", va="top",
                fontsize=DVODELNI_SLOVA - 2, color=PRIGUSENO)
    snimi(figura, "04_energetska_klasa", izlaz, format_slike)




# -------------------------------
# Glavni program
# -------------------------------
def main() -> None:
    """Čita opcije --izlaz i --format i redom crta sva četiri grafikona."""
    # opcije sam dodala da mogu da biram folder i format slika bez menjanja koda
    parser = argparse.ArgumentParser(description="Generisanje grafikona iz prečišćene baze.")
    parser.add_argument("--izlaz", default=str(FOLDER_GRAFIKONA),
                        help="folder u koji se snimaju slike")
    parser.add_argument("--format", default="png", choices=["png", "jpg"],
                        help="format izlaznih slika")
    argumenti = parser.parse_args()

    izlaz = Path(argumenti.izlaz)
    print(f"[INFO] Crtam grafikone u {izlaz}")

    # grafikone crtam redom kako su numerisani u izveštaju, od 01 do 04
    grafikon_kategorije(izlaz, argumenti.format)
    grafikon_brendovi(izlaz, argumenti.format)
    grafikon_cenovni_opsezi(izlaz, argumenti.format)
    grafikon_energetska_klasa(izlaz, argumenti.format)

    print(f"[OK] Gotovo — slike su u {izlaz}")


if __name__ == "__main__":
    main()
