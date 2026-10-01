#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
izvoz_rezultata.py — Izvršavanje upita iz upiti.sql i izvoz rezultata u Excel
                     (Zadatak 2, završni korak).

Opis:
Skripta čita upiti.sql i deli ga na pojedinačne upite (svaki se završava sa ;).
Svaki upit izvršava nad prečišćenom bazom i rezultat upisuje u zaseban list
Excel fajla, a naziv lista uzima iz oznake -- @naziv: iznad upita. Upiti
postoje samo u SQL fajlu, pa novi upit tamo odmah dobija i svoj list.

Ulazi:
    kod/analiza/upiti.sql            (ili putanja iz --upiti)
    šema preciscena

Izlazi (folder izveštaja iz zajednicko/putanje.py, ili folder iz --izlaz):
    rezultati_upita.xlsx             — jedan list po upitu

Primer poziva:
    python izvoz_rezultata.py
    python izvoz_rezultata.py --upiti upiti.sql --izlaz proba_izvoza
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

# folder kod stavljam u putanju, da bih uvezla vezu sa bazom i folder izveštaja iz zajednicko
sys.path.append(str(Path(__file__).resolve().parents[1]))
from zajednicko.baza import veza
from zajednicko.putanje import FOLDER_IZVESTAJA

# -------------------------------
# Putanje i konstante
# -------------------------------
# podrazumevano čitam upiti.sql koji stoji u istom folderu kao ova skripta
PUTANJA_UPITA = Path(__file__).resolve().parent / "upiti.sql"

# naziv upita čitam samo iz oznake oblika '-- @naziv: Top 30 televizora po ceni',
# a ne iz bilo kog komentara, jer iznad upita ima i objašnjenja u više redova
NASLOV_RE = re.compile(r"^--\s*@naziv\s*:\s*(.+?)\s*$")

# ovde su znakovi koje Excel ne dozvoljava u nazivu lista (naziv sme imati najviše 31 znak)
NEDOZVOLJENI_ZNAKOVI = re.compile(r"[:\\/?*\[\]]")


# -------------------------------
# Čitanje i deljenje SQL fajla
# -------------------------------
def procitaj_upite(putanja: Path) -> list[tuple[str, str]]:
    """
    Čita SQL fajl red po red, preskače komentare i skuplja redove dok ne naiđe
    na red koji se završava sa ';'. Vraća listu parova (naziv, sql), gde je
    naziv iz oznake @naziv, a ako je nema, 'Upit N'.
    """
    # u naslov_u_toku pamtim poslednji pročitan @naziv, a u tekuci_redovi redove upita koji još nije zatvoren
    tekst = putanja.read_text(encoding="utf-8")
    upiti, naslov_u_toku = [], None
    tekuci_redovi = []

    for red in tekst.splitlines():
        ogoljen = red.strip()

        # komentar ne šaljem bazi; iz njega uzimam samo @naziv, i to pre početka upita
        if ogoljen.startswith("--"):
            pogodak = NASLOV_RE.match(ogoljen)
            if pogodak and not tekuci_redovi:
                naslov_u_toku = pogodak.group(1)
            continue

        # prazne redove preskačem, a svaki red sa kodom dodajem tekućem upitu
        if ogoljen:
            tekuci_redovi.append(red)

        # ';' na kraju reda zatvara upit, pa naziv i redove praznim za sledeći
        if ogoljen.endswith(";"):
            sql = "\n".join(tekuci_redovi).strip()
            if sql:
                upiti.append((naslov_u_toku or f"Upit {len(upiti) + 1}", sql))
            tekuci_redovi, naslov_u_toku = [], None

    return upiti


def naziv_lista(naslov: str, redni_broj: int) -> str:
    """
    Pravi naziv Excel lista: zabranjene znakove menja razmakom, dodaje redni
    broj ispred naslova i skraćuje sve na 31 znak.
    """
    # prvo zamenim zabranjene znakove razmakom, pa više razmaka zaredom svedem na jedan
    ocisceno = NEDOZVOLJENI_ZNAKOVI.sub(" ", naslov)
    ocisceno = re.sub(r"\s+", " ", ocisceno).strip()
    # redni broj stavljam napred, da listovi u Excelu idu istim redom kao upiti u fajlu
    return f"{redni_broj}. {ocisceno}"[:31]


# -------------------------------
# Izvršavanje
# -------------------------------
def izvrsi_sve(upiti: list[tuple[str, str]]) -> list[tuple[str, pd.DataFrame]]:
    """
    Izvršava upite redom nad prečišćenom bazom i vraća listu parova (naslov,
    DataFrame). Upit koji javi grešku ispisuje sa [GRESKA] i preskače.
    """
    rezultati = []
    # otvaram jednu vezu za sve upite, umesto nove veze za svaki upit
    with veza("preciscena") as konekcija:
        for redni_broj, (naslov, sql) in enumerate(upiti, start=1):
            try:
                # rezultat čitam kurzorom, a nazive kolona uzimam iz description;
                # pd.read_sql_query bi uz psycopg2 vezu ispisivao upozorenje za SQLAlchemy
                with konekcija.cursor() as kurzor:
                    kurzor.execute(sql)
                    kolone = [opis[0] for opis in kurzor.description]
                    tabela = pd.DataFrame(kurzor.fetchall(), columns=kolone)
            except Exception as greska:
                # ako jedan upit pukne, ispišem samo prvi red greške i nastavljam sa ostalima
                print(f"[GRESKA] Upit {redni_broj} ({naslov}): {str(greska).splitlines()[0]}")
                continue
            rezultati.append((naslov, tabela))
            print(f"[OK] {redni_broj:>2}. {naslov[:60]:60} {len(tabela):>5} redova")
    return rezultati


def upisi_excel(rezultati: list[tuple[str, pd.DataFrame]], putanja: Path) -> None:
    """
    Upisuje svaki rezultat u svoj list Excel fajla (openpyxl) i svakoj koloni
    podešava širinu prema najdužem sadržaju.
    """
    putanja.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(putanja, engine="openpyxl") as pisac:
        # u svojstva fajla upisujem sebe kao autora i naslov, umesto podrazumevanog „openpyxl“
        pisac.book.properties.creator = "Anđela Spasić"
        pisac.book.properties.title = "Rezultati upita (Zadatak 2)"
        # svaki upit mi dobija svoj list, bez kolone sa indeksom iz pandas-a
        for redni_broj, (naslov, tabela) in enumerate(rezultati, start=1):
            tabela.to_excel(pisac, sheet_name=naziv_lista(naslov, redni_broj), index=False)

            # širina = najduži od naslova i prvih 200 vrednosti + 2, a najviše 60,
            # da tabela može da se čita bez ručnog razvlačenja kolona
            list_excela = pisac.sheets[naziv_lista(naslov, redni_broj)]
            for redni_kolone, kolona in enumerate(tabela.columns, start=1):
                najduzi = max([len(str(kolona))] +
                              [len(str(v)) for v in tabela[kolona].head(200)]) + 2
                # slovo kolone (A, B, C...) uzimam iz ćelije u prvom redu
                list_excela.column_dimensions[
                    list_excela.cell(row=1, column=redni_kolone).column_letter
                ].width = min(najduzi, 60)
    print(f"[OK] Excel: {putanja}")



def main() -> None:
    """Čita opcije --upiti i --izlaz, izvršava upite i pravi Excel fajl."""
    # obe opcije imaju podrazumevanu vrednost, pa skripta radi i bez argumenata
    parser = argparse.ArgumentParser(description="Izvršavanje SQL upita i izvoz rezultata.")
    parser.add_argument("--upiti", default=str(PUTANJA_UPITA), help="putanja do SQL fajla")
    parser.add_argument("--izlaz", default=str(FOLDER_IZVESTAJA), help="folder za izlazni Excel fajl")
    argumenti = parser.parse_args()

    upiti = procitaj_upite(Path(argumenti.upiti))
    print(f"[INFO] Pronađeno {len(upiti)} upita u {argumenti.upiti}")

    # ako nijedan upit nije prošao, Excel fajl ne pravim
    rezultati = izvrsi_sve(upiti)
    if not rezultati:
        print("[GRESKA] Nijedan upit nije uspešno izvršen.")
        return

    # za Excel treba openpyxl; bez njega samo javljam da fajl nije napravljen
    izlaz = Path(argumenti.izlaz)
    try:
        import openpyxl                         # samo proveravam da postoji
    except ImportError:
        print("[GRESKA] openpyxl nije instaliran, pa Excel fajl nije napravljen.")
        return
    upisi_excel(rezultati, izlaz / "rezultati_upita.xlsx")


if __name__ == "__main__":
    main()
