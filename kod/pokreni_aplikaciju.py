#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pokreni_aplikaciju.py — Pokretanje aplikacije na računaru bez PostgreSQL servera.

Opis:
Skripta je za računar na kome nema PostgreSQL servera. Prvo proverava da li
Python ima biblioteke numpy, pandas i matplotlib (prozor aplikacije je
tkinter, deo standardnog Python-a).
Zatim pita za MySQL: ako se unese korisničko ime i lozinka, a PyMySQL je
instaliran, baze se (samo prvi put) prepišu iz fajlova u MySQL i aplikacija
čita iz njega; ako se samo pritisne Enter ili MySQL ne odgovori, aplikacija
čita kopiju baze iz fajla baza/sqlite/psz_preciscena.sqlite. Na kraju otvara
prozor aplikacije.

Ulazi:
    baza/sqlite/*.sqlite, izvestaj/modeli/regresija_model.json

Izlazi:
    prozor aplikacije; uz MySQL i baze primarna i preciscena

Primer poziva:
    python kod/pokreni_aplikaciju.py
    python kod/pokreni_aplikaciju.py --baza fajl
    python kod/pokreni_aplikaciju.py --baza mysql --korisnik root
    (ili otvoriti ovaj fajl u IDLE ili PyCharm-u i pokrenuti ga)
"""

from __future__ import annotations

import argparse
import getpass
import importlib
import os
import sys
from importlib import metadata
from pathlib import Path

# kad izlaz nije konzola (npr. preusmeren u fajl), Windows ispisuje u kodnoj strani bez č i ć,
# pa bi print pukao; zato izlaz prebacujem na UTF-8. IDLE to ne podržava, pa ga preskačem.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

# folder kod stavljam na početak putanje, da uvoz paketa zajednicko radi odakle god pokrenem skriptu
KOD = Path(__file__).resolve().parent
sys.path.insert(0, str(KOD))

# biblioteke koje moraju biti instalirane; tkinter je deo Python-a, a PyMySQL treba samo za MySQL
POTREBNE = ["numpy", "pandas", "matplotlib", "tkinter"]



# -------------------------------
# Provera računara
# -------------------------------
def proveri_python() -> bool:
    """Ispisuje verziju Python-a i biblioteka i vraća False ako nešto neophodno fali."""
    # prvo ispisujem verziju i putanju Python-a, da se vidi koji je pokrenut
    print(f"[INFO] Python {sys.version.split()[0]} ({sys.executable})")
    if sys.version_info < (3, 10):
        print("[GRESKA] Potreban je Python 3.10 ili noviji.")
        return False

    # Svaku biblioteku probam da uvezem, a verziju čitam iz metapodataka; tkinter ih nema, jer je deo Python-a.
    sve_ima = True
    for ime in POTREBNE + ["pymysql"]:
        try:
            importlib.import_module(ime)
            try:
                verzija = metadata.version(ime)
            except metadata.PackageNotFoundError:
                verzija = "deo Python-a" if ime == "tkinter" else ""
            print(f"[OK] {ime:11} {verzija}")
        except ImportError:
            # PyMySQL nije obavezan: bez njega ostaje baza iz fajla
            if ime == "pymysql":
                print(f"[INFO] {ime:11} nije instaliran (MySQL se ne može koristiti, baza se čita iz fajla)")
            else:
                print(f"[GRESKA] {ime:11} nije instaliran")
                sve_ima = False
    if not sve_ima:
        print("[GRESKA] Bez ovih biblioteka aplikacija ne može da radi; potrebno je instalirati ono što fali "
              "(vidi kod/requirements.txt). Slike aplikacije su u izveštaju, u poglavljima 5, 6 i 7.")
    return sve_ima


# -------------------------------
# Izbor baze
# -------------------------------
def izaberi_bazu(argumenti) -> str:
    """
    Pita za MySQL (ili čita opcije) i vraća "mysql" ako veza radi i baze su
    učitane, a inače "sqlite". Podešava promenljive okruženja koje čita baza.py.
    """
    # module iz paketa zajednicko uvozim tek ovde, kad mi zatrebaju za izbor baze; putanju do foldera kod sam podesila na vrhu fajla
    from zajednicko import kopija_baze
    from zajednicko.baza import mysql_konekcija

    # ako način nije zadat opcijom, pitam korisnika; prazan unos znači bazu iz fajla
    nacin = argumenti.baza
    korisnik = argumenti.korisnik
    if nacin is None:
        korisnik = input("MySQL korisnik (samo Enter = baza iz fajla, bez MySQL-a): ").strip()
        nacin = "mysql" if korisnik else "fajl"

    if nacin == "mysql":
        # lozinku čitam preko getpass, da se ne vidi na ekranu dok se kuca
        lozinka = argumenti.lozinka
        if lozinka is None:
            lozinka = getpass.getpass("MySQL lozinka (ne prikazuje se dok kucaš): ")
        os.environ.update({
            "PSZ_MYSQL_HOST": argumenti.host, "PSZ_MYSQL_PORT": str(argumenti.mysql_port),
            "PSZ_MYSQL_USER": korisnik or "root", "PSZ_MYSQL_PASSWORD": lozinka,
        })
        # Parametre sam upisala u okruženje, jer ih baza.py čita odatle. Vezu probam sa rokom od 5 sekundi;
        # ako uspe, punim MySQL (ucitaj_u_mysql to preskače kad je već pun), a ako bilo šta pukne, prelazim na fajl.
        try:
            mysql_konekcija(connect_timeout=5).close()
            print("[INFO] MySQL se javio. Prvi put se baze prepisuju iz fajlova (do minut)...")
            kopija_baze.ucitaj_u_mysql()
            os.environ["PSZ_BAZA"] = "mysql"
            return "mysql"
        except Exception as greska:
            print(f"[UPOZORENJE] MySQL nije dostupan ({greska}); čitam bazu iz fajla.")

    # ovde stižem i kad je izabran fajl i kad MySQL nije uspeo
    os.environ["PSZ_BAZA"] = "sqlite"
    return "sqlite"


# -------------------------------
# Pokretanje aplikacije
# -------------------------------
def main() -> None:
    """Proverava računar, bira bazu i pokreće aplikaciju."""
    # sve opcije su neobavezne; bez njih skripta sama pita šta joj treba
    parser = argparse.ArgumentParser(description="Pokretanje aplikacije bez PostgreSQL servera (baza iz fajla ili MySQL).")
    parser.add_argument("--baza", choices=["fajl", "mysql"], default=None,
                        help="odakle se čita baza; bez opcije skripta pita")
    parser.add_argument("--korisnik", default=None, help="MySQL korisnik")
    parser.add_argument("--lozinka", default=None, help="MySQL lozinka (bez opcije skripta pita)")
    parser.add_argument("--host", default="localhost", help="MySQL server")
    parser.add_argument("--mysql_port", type=int, default=3306, help="MySQL port")
    argumenti = parser.parse_args()

    # kad fali biblioteka, čekam Enter, da se prozor ne zatvori pre nego što se pročita poruka
    if not proveri_python():
        if sys.stdin.isatty():
            input("Pritisni Enter za kraj.")
        return

    izvor = izaberi_bazu(argumenti)
    print(f"[INFO] Baza: {'MySQL' if izvor == 'mysql' else 'fajl baza/sqlite/psz_preciscena.sqlite'}")

    # app.py uvozim tek kad je PSZ_BAZA podešena, pa odmah učitavam podatke
    sys.path.insert(0, str(KOD / "app"))
    import app
    app.dohvati_stanje()

    app.pokreni()


if __name__ == "__main__":
    main()
