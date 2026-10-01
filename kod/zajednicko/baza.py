#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
baza.py — Zajednički modul za povezivanje na baze projekta.

Opis:
Projekat koristi dve odvojene baze: primarnu za sirove zapise iz parsera
(Zadatak 1) i prečišćenu za prečišćene i spojene podatke (Zadatak 2).
Zadatak 2 traži da se prečišćeni podaci sačuvaju „u novoj, revidiranoj bazi
podataka“, pa je to posebna baza, a ne nova šema u istoj bazi.

Glavna baza je PostgreSQL. Da bi projekat mogao da se
pokrene i na računaru bez PostgreSQL servera, iste podatke može da
čita i iz MySQL-a ili iz kopije u fajlovima baza/sqlite/*.sqlite (SQLite je
ugrađen u Python, pa za njega ne treba ni server ni instalacija). Izvor bira
promenljiva PSZ_BAZA; ako nije zadata, prvo probam PostgreSQL, a ako se on ne
javi, čitam kopiju iz fajla. Kopija iz fajla se otvara samo za čitanje.

Funkcija veza() nema podrazumevanu bazu, da zaboravljen argument ne bi poslao
upit u pogrešnu bazu, nego da odmah javi grešku.

Promenljive okruženja:
    PSZ_BAZA           postgres, mysql ili sqlite (podrazumevano: sam bira)
    PSZ_DB_HOST        PostgreSQL server (podrazumevano: localhost)
    PSZ_DB_PORT        (podrazumevano: 5433)
    PSZ_DB_USER        (podrazumevano: psz)
    PSZ_DB_PASSWORD    (podrazumevano: psz2026)
    PSZ_DB_PRIMARNA    (podrazumevano: psz_primarna)
    PSZ_DB_PRECISCENA  (podrazumevano: psz_preciscena)
    PSZ_MYSQL_HOST     MySQL server (podrazumevano: localhost)
    PSZ_MYSQL_PORT     (podrazumevano: 3306)
    PSZ_MYSQL_USER     (podrazumevano: root)
    PSZ_MYSQL_PASSWORD (podrazumevano: prazno)

Primer upotrebe:
    from zajednicko.baza import veza

    with veza("preciscena") as konekcija:
        with konekcija.cursor() as kurzor:
            kurzor.execute("SELECT COUNT(*) FROM preciscena.proizvodi")
            print(kurzor.fetchone()[0])
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# -------------------------------
# Parametri povezivanja
# -------------------------------
# PostgreSQL: server, port, korisnik i lozinka su mi isti za obe baze, razlikuje se samo naziv baze.
ZAJEDNICKI_PARAMETRI = {
    "host":     os.environ.get("PSZ_DB_HOST", "localhost"),
    "port":     int(os.environ.get("PSZ_DB_PORT", "5433")),
    "user":     os.environ.get("PSZ_DB_USER", "psz"),
    "password": os.environ.get("PSZ_DB_PASSWORD", "psz2026"),
}

# ovde povezujem kratko ime koje prosleđujem funkciji veza() sa stvarnim nazivom baze u PostgreSQL-u
NAZIVI_BAZA = {
    "primarna":   os.environ.get("PSZ_DB_PRIMARNA", "psz_primarna"),
    "preciscena": os.environ.get("PSZ_DB_PRECISCENA", "psz_preciscena"),
}

# U MySQL-u je baza isto što i šema u PostgreSQL-u, pa sam baze nazvala primarna i
# preciscena; tako mi upit "SELECT ... FROM preciscena.proizvodi" radi bez izmene.
NAZIVI_MYSQL_BAZA = {"primarna": "primarna", "preciscena": "preciscena"}

# kopije baza držim u fajlovima: baza/sqlite/psz_primarna.sqlite i psz_preciscena.sqlite
FOLDER_SQLITE = Path(__file__).resolve().parents[2] / "baza" / "sqlite"


# tri izvora koja podržavam; izabrani pamtim u _izabrani_izvor, da ne proveravam svaki put
IZVORI = ("postgres", "mysql", "sqlite")
_izabrani_izvor = None


def parametri_mysql() -> dict:
    """Čita parametre za MySQL iz promenljivih okruženja i vraća ih kao rečnik."""
    # za MySQL sam ostavila uobičajene vrednosti lokalne instalacije: root bez lozinke na 3306
    return {
        "host":     os.environ.get("PSZ_MYSQL_HOST", "localhost"),
        "port":     int(os.environ.get("PSZ_MYSQL_PORT", "3306")),
        "user":     os.environ.get("PSZ_MYSQL_USER", "root"),
        "password": os.environ.get("PSZ_MYSQL_PASSWORD", ""),
    }


def uvezi_pymysql():
    """Vraća modul pymysql; ako nije instaliran, ImportError se dalje tumači kao „MySQL nije dostupan“."""
    import pymysql
    return pymysql


def mysql_konekcija(**dodatno):
    """
    Otvara vezu sa MySQL serverom sa parametrima iz parametri_mysql() i vraća je.
    MySQL 8 podrazumevano proverava lozinku postupkom caching_sha2_password, koji
    bez šifrovane veze traži biblioteku cryptography. Zato tražim šifrovanu vezu
    (TLS, bez provere sertifikata, jer je server lokalni); ako je server nema,
    PyMySQL nastavlja običnom vezom.
    """
    # utf8mb4 sam stavila da mi prođu sva slova (č, ć, ž...) u nazivima proizvoda;
    # kroz dodatno stižu naziv baze i autocommit
    pymysql = uvezi_pymysql()
    return pymysql.connect(charset="utf8mb4", ssl={"ca": None}, **parametri_mysql(), **dodatno)


# -------------------------------
# Izbor izvora podataka
# -------------------------------
def _postgres_se_javlja() -> bool:
    """Proverava da li je psycopg2 instaliran i da li se PostgreSQL javlja u roku od 3 sekunde."""
    # Svaku grešku (nema biblioteke, server ugašen, pogrešna lozinka) tumačim kao „ne javlja se“.
    try:
        import psycopg2
        konekcija = psycopg2.connect(dbname=NAZIVI_BAZA["preciscena"], connect_timeout=3,
                                     **ZAJEDNICKI_PARAMETRI)
        konekcija.close()
        return True
    except Exception:
        return False


def izvor() -> str:
    """
    Vraća izvor podataka: vrednost iz PSZ_BAZA, a ako nije zadata, "postgres"
    kad se PostgreSQL javlja, inače "sqlite". Izbor se pamti za ceo program.
    """
    global _izabrani_izvor
    # biram samo pri prvom pozivu; posle vraćam zapamćeni izvor
    if _izabrani_izvor is None:
        zadato = os.environ.get("PSZ_BAZA", "").strip().lower()
        # ako je izvor zadat ručno, prihvatam samo jedan od tri poznata
        if zadato:
            if zadato not in IZVORI:
                raise ValueError(f"PSZ_BAZA mora biti jedno od: {', '.join(IZVORI)}")
            _izabrani_izvor = zadato
        # inače prvo probam PostgreSQL, a kopija iz fajla mi je rezerva
        elif _postgres_se_javlja():
            _izabrani_izvor = "postgres"
        else:
            _izabrani_izvor = "sqlite"
            print(f"[INFO] PostgreSQL se ne javlja, pa čitam kopiju baze iz fajla ({FOLDER_SQLITE})")
    return _izabrani_izvor


# -------------------------------
# SQLite: omotač da se kurzor koristi u with bloku, kao kod ostalih baza
# -------------------------------
class _SqliteKurzor:
    """Kurzor SQLite-a koji može da stoji u with bloku; sve ostalo prosleđuje pravom kurzoru."""

    def __init__(self, kurzor):
        # čuvam pravi sqlite3 kurzor kome posle sve prosleđujem
        self._kurzor = kurzor

    def __enter__(self):
        # with blok mi dobija baš ovaj omotač, a ne goli kurzor
        return self

    def __exit__(self, *greska):
        # na izlasku iz with bloka zatvaram kurzor, kao što to rade psycopg2 i PyMySQL
        self._kurzor.close()

    def __getattr__(self, ime):
        # execute, fetchone, fetchall i ostalo tražim na pravom kurzoru
        return getattr(self._kurzor, ime)


class _SqliteVeza:
    """Veza sa SQLite fajlom sa istim metodama kao veza sa PostgreSQL-om i MySQL-om."""

    def __init__(self, konekcija):
        # pamtim sqlite3 vezu na koju je fajl zakačen
        self._konekcija = konekcija

    def cursor(self):
        # vraćam svoj omotač, da kurzor može da stoji u with bloku
        return _SqliteKurzor(self._konekcija.cursor())

    # commit, rollback i close samo prosleđujem pravoj sqlite3 vezi
    def commit(self):
        self._konekcija.commit()

    def rollback(self):
        self._konekcija.rollback()

    def close(self):
        self._konekcija.close()


def _sqlite_veza(baza: str) -> _SqliteVeza:
    """
    Otvara fajl psz_<baza>.sqlite samo za čitanje i kači ga pod imenom baze, pa
    upit "SELECT ... FROM preciscena.proizvodi" radi isto kao u PostgreSQL-u.
    """
    fajl = FOLDER_SQLITE / f"psz_{baza}.sqlite"
    if not fajl.exists():
        raise FileNotFoundError(f"Nema kopije baze {fajl}")
    # Otvaram praznu bazu u memoriji, pa fajl kačim sa ATTACH pod imenom baze;
    # mode=ro u URI-ju mi garantuje da u kopiju ništa ne može da se upiše.
    konekcija = sqlite3.connect(":memory:", uri=True)
    konekcija.execute(f"ATTACH DATABASE ? AS {baza}", (f"{fajl.as_uri()}?mode=ro",))
    return _SqliteVeza(konekcija)


# -------------------------------
# Veza sa bazom
# -------------------------------
@contextmanager
def veza(baza: str):
    """
    Otvara konekciju ka bazi "primarna" ili "preciscena" (u izvoru koji vraća
    izvor()) i daje je with bloku. Posle bloka potvrđuje izmene (commit), posle
    greške ih poništava (rollback), a konekciju zatvara u oba slučaja.
    """
    # pogrešno ime baze odmah prijavljujem, pre nego što bilo šta otvorim
    if baza not in NAZIVI_BAZA:
        raise ValueError(f"Nepoznata baza '{baza}'. Dozvoljeno: {', '.join(NAZIVI_BAZA)}")

    # ovde otvaram vezu prema izabranom izvoru; psycopg2 uvozim tek kad mi zaista treba
    if izvor() == "postgres":
        import psycopg2
        konekcija = psycopg2.connect(dbname=NAZIVI_BAZA[baza], **ZAJEDNICKI_PARAMETRI)
    elif izvor() == "mysql":
        konekcija = mysql_konekcija(database=NAZIVI_MYSQL_BAZA[baza])
    else:
        konekcija = _sqlite_veza(baza)

    # posle with bloka potvrđujem izmene, kod greške ih poništavam i grešku puštam dalje
    try:
        yield konekcija
        konekcija.commit()
    except Exception:
        konekcija.rollback()
        raise
    finally:
        konekcija.close()


def proveri_vezu() -> bool:
    """
    Za svaku bazu pokušava kratak upit (ime baze i verzija servera) i ispisuje da
    li je uspeo. Vraća True samo ako odgovore obe baze.
    """
    # svaki izvor ima svoj način da vrati ime baze i verziju, pa sam napisala tri upita
    upiti = {
        "postgres": "SELECT current_database(), version()",
        "mysql":    "SELECT DATABASE(), VERSION()",
        "sqlite":   "SELECT 'fajl', 'SQLite ' || sqlite_version()",
    }
    sve_radi, verzija = True, ""
    # proveravam obe baze redom; ako jedna ne radi, i dalje probam drugu
    for baza in NAZIVI_BAZA:
        try:
            with veza(baza) as konekcija:
                with konekcija.cursor() as kurzor:
                    kurzor.execute(upiti[izvor()])
                    ime_baze, verzija = kurzor.fetchone()
            print(f"[OK] {baza:10} → {izvor()}, baza '{ime_baze}'")
        except Exception as greska:
            print(f"[GRESKA] {baza:10} → {izvor()}: {str(greska).strip()}")
            sve_radi = False
    # od duge oznake verzije ispisujem samo deo do prvog zareza
    if sve_radi:
        print(f"[INFO] {str(verzija).split(',')[0]}")
    return sve_radi


def sifarnik_prodavnica() -> dict:
    """Čita tabelu primarna.prodavnice i vraća rečnik {šifra: id}, npr. {'winwin': 1, 'gigatron': 2}."""
    # rečnik mi treba pri upisu (upis_u_bazu.py i indekser.py), da po šifri prodavnice nađem njen id
    with veza("primarna") as konekcija:
        with konekcija.cursor() as kurzor:
            kurzor.execute("SELECT sifra, id FROM primarna.prodavnice")
            return {sifra: ident for sifra, ident in kurzor.fetchall()}


if __name__ == "__main__":
    # kad pokrenem ovaj fajl direktno, samo proverim da li mi se obe baze javljaju
    proveri_vezu()
