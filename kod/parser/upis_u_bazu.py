#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
upis_u_bazu.py — Parsiranje snimljenih stranica i punjenje primarne baze
                 (Zadatak 1, završni korak).

Opis:
Skripta prolazi kroz stranice koje je indekser snimio, za svaku poziva parser
prodavnice (parser_magento za winwin.rs, parser_gigatron za gigatron.rs) i
upisuje rezultat u šemu primarna, u paketima od po 500 proizvoda. Parsiranje sam
odvojila od preuzimanja, koje traje satima i opterećuje server prodavnice, pa se
posle izmene parsera ceo upis ponovi za pedesetak minuta, bez novih zahteva.
Ponovno pokretanje ne pravi duplikate, jer se proizvod prepoznaje po paru
(prodavnica, url) i postojeći zapis se ažurira (ON CONFLICT ... DO UPDATE).

Ulazi:
    ../indekser/preuzeto/<prodavnica>/*.html.gz

Izlazi:
    tabele primarna.proizvodi i primarna.karakteristike
    ispis stanja baze iz pogleda primarna.v_pregled

Primer poziva:
    python upis_u_bazu.py --prodavnica winwin
    python upis_u_bazu.py --prodavnica gigatron --ogranicenje 500
    python upis_u_bazu.py --prodavnica sve
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

# u putanju dodajem kod/, folder indeksera i ovaj folder, da bih uvezla bazu,
# podešavanja i oba parsera bez pravljenja paketa
sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parents[1] / "indekser"))
sys.path.append(str(Path(__file__).resolve().parent))

from zajednicko.baza import veza, sifarnik_prodavnica
from zajednicko.upiti import UPIT_PROIZVOD, UPIT_DATUM_PREUZIMANJA
import podesavanja as pod
import parser_magento
import parser_gigatron

# -------------------------------
# Konstante
# -------------------------------
# snimljene stranice čitam iz kod/indekser/preuzeto/<prodavnica>/
FOLDER_PREUZETO = Path(__file__).resolve().parents[1] / "indekser" / pod.FOLDER_HTML
VELICINA_PAKETA = 500        # ovoliko proizvoda upisujem u jednoj transakciji

# vrednošću 'parser' iz podešavanja prodavnice biram modul; oba modula imaju
# iste funkcije procitaj_html i parsiraj, pa ih dalje koristim isto
PARSERI = {
    "magento":  parser_magento,
    "gigatron": parser_gigatron,
}


# -------------------------------
# Upis jednog paketa proizvoda
# -------------------------------
def upisi_paket(paket: list[dict], prodavnica_id: int) -> None:
    """
    Upisuje paket proizvoda u jednoj transakciji: za svaki proizvod izvršava
    UPIT_PROIZVOD, uzima vraćeni id, briše njegove stare karakteristike i upisuje nove.
    """
    # prazan paket dobijem kad nijedan proizvod nije prihvaćen ili je broj deljiv sa 500,
    # pa tada ni ne otvaram vezu ka bazi
    if not paket:
        return

    with veza("primarna") as konekcija:
        with konekcija.cursor() as kurzor:
            for podaci in paket:
                # karakteristike idu u posebnu tabelu, pa ih vadim iz rečnika proizvoda,
                # a dodajem prodavnica_id, koji upit očekuje kao imenovani parametar
                karakteristike = podaci.pop("karakteristike", [])
                podaci["prodavnica_id"] = prodavnica_id

                # UPIT_PROIZVOD vraća id proizvoda, i kad ga upisuje i kad ga ažurira
                kurzor.execute(UPIT_PROIZVOD, podaci)
                proizvod_id = kurzor.fetchone()[0]

                # karakteristike brišem i upisujem iznova, da posle izmene parsera ili
                # specifikacije na sajtu ne ostanu stare vrednosti; naziv skraćujem
                # na 200, a vrednost na 2.000 znakova
                kurzor.execute("DELETE FROM primarna.karakteristike WHERE proizvod_id = %s",
                               (proizvod_id,))
                if karakteristike:
                    kurzor.executemany(
                        """INSERT INTO primarna.karakteristike (proizvod_id, naziv, vrednost)
                           VALUES (%s, %s, %s)""",
                        [(proizvod_id, naziv[:200], vrednost[:2000]) for naziv, vrednost in karakteristike],
                    )


# -------------------------------
# Obrada jedne prodavnice
# -------------------------------
def obradi_prodavnicu(sifra: str, ogranicenje: int | None) -> None:
    """
    Funkcija bira parser prodavnice, parsira sve (ili prvih `ogranicenje`) snimljene
    stranice i prihvaćene proizvode upisuje u paketima. Na kraju ispisuje koliko je
    upisano, odbačeno i neuspelo, i šest najčešćih kategorija.
    """
    # po šifri prodavnice nalazim njena podešavanja i modul parsera
    podaci_prodavnice = pod.PRODAVNICE[sifra]
    modul = PARSERI[podaci_prodavnice["parser"]]

    folder = FOLDER_PREUZETO / sifra
    if not folder.exists():
        print(f"[GRESKA] Ne postoji folder {folder}. Prvo pokreni indekser.")
        return

    # fajlove sortiram, da redosled obrade bude isti pri svakom pokretanju
    fajlovi = sorted(folder.glob("*.html.gz"))
    if ogranicenje:
        fajlovi = fajlovi[:ogranicenje]

    prodavnica_id = sifarnik_prodavnica()[sifra]
    print(f"[INFO] {podaci_prodavnice['naziv']}: parsiram {len(fajlovi):,} snimljenih stranica "
          f"({podaci_prodavnice['parser']} parser)")

    # Counter mi služi i za brojače ishoda i za prebrojavanje kategorija
    pocetak = time.perf_counter()
    paket, brojaci = [], Counter()
    kategorije = Counter()
    prihvacene_adrese = []

    for redni_broj, fajl in enumerate(fajlovi, start=1):
        # stranica na kojoj parser pukne se broji i preskače; ispisujem samo prvih 5 grešaka
        try:
            proizvod = modul.parsiraj(modul.procitaj_html(fajl))
        except Exception as greska:
            brojaci["greska_parsiranja"] += 1
            if brojaci["greska_parsiranja"] <= 5:
                print(f"[GRESKA] {fajl.name}: {greska}")
            continue

        # None dobijem kad parser ne prepozna proizvod (nema adresu ili naziv, a kod
        # Gigatrona ni blok Product) ili kad Gigatronov proizvod nije bela tehnika
        if not proizvod:
            brojaci["odbaceno"] += 1
            continue
        if not proizvod.get("naziv"):
            brojaci["bez_naziva"] += 1
            continue

        # prihvaćen proizvod brojim po kategoriji i stavljam u paket
        kategorije[proizvod.get("kategorija") or "(nepoznato)"] += 1
        prihvacene_adrese.append(proizvod["url"])
        paket.append(proizvod)
        brojaci["prihvaceno"] += 1

        # pun paket upisujem odmah, da mi u memoriji ne stoje svi proizvodi
        if len(paket) >= VELICINA_PAKETA:
            upisi_paket(paket, prodavnica_id)
            paket = []
            print(f"[INFO] {redni_broj:,}/{len(fajlovi):,} obrađeno, "
                  f"upisano {brojaci['prihvaceno']:,}, odbačeno {brojaci['odbaceno']:,}")

    # posle petlje upisujem i poslednji paket, koji nije stigao do 500 proizvoda
    upisi_paket(paket, prodavnica_id)

    # vreme preuzimanja prepisujem iz dnevnika indeksiranja, jer je parsiranje bilo kasnije
    with veza("primarna") as konekcija:
        with konekcija.cursor() as kurzor:
            kurzor.execute(UPIT_DATUM_PREUZIMANJA, (prodavnica_id,))
            print(f"[INFO] Vreme preuzimanja iz dnevnika upisano za {kurzor.rowcount:,} proizvoda")
            # u bazi ostavljam samo proizvode koje je parser sada prihvatio; brišem jedino kad
            # sam obradila sve stranice, kad sam nešto prihvatila i kad nije bilo ni jedne
            # greške, da kratka proba ili greška na jednoj stranici ne obrišu tačan zapis
            if prihvacene_adrese and not ogranicenje and not brojaci["greska_parsiranja"]:
                kurzor.execute("DELETE FROM primarna.proizvodi WHERE prodavnica_id = %s AND NOT (url = ANY(%s))",
                               (prodavnica_id, prihvacene_adrese))
                print(f"[INFO] Obrisano {kurzor.rowcount:,} proizvoda koje parser ne prihvata")

    # u završnom ispisu dajem brojače ishoda i šest kategorija sa najviše proizvoda
    minuti = (time.perf_counter() - pocetak) / 60
    print(f"[OK] {podaci_prodavnice['naziv']}: upisano {brojaci['prihvaceno']:,} proizvoda, "
          f"odbačeno {brojaci['odbaceno']:,}, bez naziva {brojaci['bez_naziva']:,}, "
          f"greške {brojaci['greska_parsiranja']:,}  (za {minuti:.1f} min)")
    print("[INFO] najzastupljenije kategorije: "
          + ", ".join(f"{naziv} ({broj})" for naziv, broj in kategorije.most_common(6)))


# -------------------------------
# Glavni program
# -------------------------------
def main() -> None:
    """Čita argumente, obrađuje izabrane prodavnice i na kraju ispisuje stanje primarne baze."""
    # bez --prodavnica obrađujem obe, a --ogranicenje mi služi za kratku probu
    parser = argparse.ArgumentParser(description="Parsiranje snimljenih stranica i upis u primarnu bazu.")
    parser.add_argument("--prodavnica", default="sve",
                        help="šifra prodavnice (winwin ili gigatron) ili 'sve'")
    parser.add_argument("--ogranicenje", type=int, default=None,
                        help="maksimalan broj stranica za obradu (za probu)")
    argumenti = parser.parse_args()

    # nepoznatu šifru samo javljam i prelazim na sledeću, bez prekida programa
    sifre = list(pod.PRODAVNICE) if argumenti.prodavnica == "sve" else [argumenti.prodavnica]
    for sifra in sifre:
        if sifra not in pod.PRODAVNICE:
            print(f"[GRESKA] Nepoznata prodavnica '{sifra}'")
            continue
        obradi_prodavnicu(sifra, argumenti.ogranicenje)

    # na kraju pravim kratak pregled po prodavnicama iz pogleda primarna.v_pregled
    with veza("primarna") as konekcija:
        with konekcija.cursor() as kurzor:
            kurzor.execute("SELECT prodavnica, broj_proizvoda, sa_cenom, broj_brendova, "
                           "broj_kategorija FROM primarna.v_pregled")
            print("\n[INFO] Stanje primarne baze:")
            print(f"       {'prodavnica':14} {'proizvoda':>10} {'sa cenom':>10} {'brendova':>10} {'kategorija':>11}")
            for red in kurzor.fetchall():
                print(f"       {red[0]:14} {red[1]:>10,} {red[2]:>10,} {red[3]:>10,} {red[4]:>11,}")


if __name__ == "__main__":
    main()
