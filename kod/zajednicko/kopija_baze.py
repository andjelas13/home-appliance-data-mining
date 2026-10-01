#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kopija_baze.py — Kopija baza u fajlovima (SQLite) i njeno učitavanje u MySQL.

Opis:
Glavna baza projekta je PostgreSQL. Da bi projekat mogao
da se pokrene i na računaru bez PostgreSQL servera, ova skripta sa opcijom --sqlite
prepisuje obe baze iz PostgreSQL-a u fajlove baza/sqlite/psz_primarna.sqlite i
psz_preciscena.sqlite. Sa opcijom --mysql te fajlove učitava u MySQL, u baze
primarna i preciscena. Redovi se svuda upisuju istim redom kojim su u
PostgreSQL-u, jer od redosleda redova zavisi podela na trening i test skup.
Tabele u kopijama nemaju indekse po koloni cena_min, da čitanje ne bi išlo
redom cena umesto redom upisa.

Ulazi:
    --sqlite: baze psz_primarna i psz_preciscena u PostgreSQL-u
    --mysql:  fajlovi baza/sqlite/*.sqlite

Izlazi:
    --sqlite: baza/sqlite/psz_primarna.sqlite i baza/sqlite/psz_preciscena.sqlite
    --mysql:  baze primarna i preciscena na MySQL serveru (parametri iz PSZ_MYSQL_*)

Primer poziva:
    python kopija_baze.py --sqlite
    python kopija_baze.py --mysql
"""

from __future__ import annotations

import argparse
import datetime
import decimal
import sqlite3
import sys
import time
from pathlib import Path

# dodajem folder kod na putanju, da mogu da uvezem paket zajednicko i kad skriptu pokrenem direktno
sys.path.append(str(Path(__file__).resolve().parents[1]))
from zajednicko.baza import (FOLDER_SQLITE, NAZIVI_BAZA, ZAJEDNICKI_PARAMETRI,
                             mysql_konekcija, uvezi_pymysql)

# -------------------------------
# Tabele i pogledi
# -------------------------------
# tabele redom kojim ih prepisujem, po bazi
TABELE = {
    "primarna":   ["prodavnice", "proizvodi", "karakteristike", "dnevnik_indeksiranja"],
    "preciscena": ["proizvodi", "poreklo", "dnevnik_ciscenja"],
}

# tip kolone iz PostgreSQL-a → tip u SQLite fajlu; iz tog tipa posle biram tip u MySQL-u
TIPOVI_SQLITE = {
    "integer": "INTEGER", "smallint": "INTEGER", "bigint": "INTEGER",
    "numeric": "REAL", "real": "REAL", "double precision": "REAL",
    "boolean": "BOOLEAN", "text": "TEXT", "timestamp with time zone": "TIMESTAMP",
}
# vreme u MySQL-u čuvam kao tekst, jer ga SQLite kopija već ima kao ISO tekst
TIPOVI_MYSQL = {"INTEGER": "BIGINT", "REAL": "DOUBLE", "BOOLEAN": "TINYINT(1)",
                "TEXT": "LONGTEXT", "TIMESTAMP": "VARCHAR(40)"}

# Poglede sam prepisala iz šema u folderu baza, samo bez imena šeme ispred
# tabele, jer ih u SQLite fajlu i u MySQL-u pravim unutar same baze.
POGLEDI = {
    "primarna": {
        "v_pregled": """
            SELECT  pr.sifra AS prodavnica, COUNT(*) AS broj_proizvoda, COUNT(p.cena) AS sa_cenom,
                    COUNT(DISTINCT p.brend) AS broj_brendova, COUNT(DISTINCT p.kategorija) AS broj_kategorija,
                    MIN(p.datum_preuzimanja) AS prvo_preuzimanje, MAX(p.datum_preuzimanja) AS poslednje_preuzimanje
            FROM proizvodi p JOIN prodavnice pr ON pr.id = p.prodavnica_id
            GROUP BY pr.sifra ORDER BY broj_proizvoda DESC""",
    },
    "preciscena": {
        "v_poredjenje_cena": """
            WITH po_prodavnici AS (
                SELECT preciscen_id, prodavnica, MIN(cena) AS cena
                FROM poreklo WHERE cena IS NOT NULL GROUP BY preciscen_id, prodavnica
            ), raspon AS (
                SELECT preciscen_id, MIN(cena) AS niza_cena, MAX(cena) AS visa_cena
                FROM po_prodavnici GROUP BY preciscen_id HAVING COUNT(*) > 1
            )
            SELECT  p.id, p.brend, p.naziv, p.kategorija, r.niza_cena, r.visa_cena,
                    r.visa_cena - r.niza_cena AS razlika_dinara,
                    ROUND((r.visa_cena - r.niza_cena) / r.niza_cena * 100, 2) AS razlika_procenat,
                    p.izvori
            FROM raspon r JOIN proizvodi p ON p.id = r.preciscen_id
            ORDER BY razlika_procenat DESC""",
        "v_popunjenost": """
            SELECT  kategorija, COUNT(*) AS ukupno,
                    ROUND(100.0 * COUNT(cena_min) / COUNT(*), 1) AS cena_pct,
                    ROUND(100.0 * COUNT(energetska_klasa) / COUNT(*), 1) AS energetska_pct,
                    ROUND(100.0 * COUNT(dijagonala_inch) / COUNT(*), 1) AS dijagonala_pct,
                    ROUND(100.0 * COUNT(zapremina_l) / COUNT(*), 1) AS zapremina_pct,
                    ROUND(100.0 * COUNT(kapacitet_pranja_kg) / COUNT(*), 1) AS kapacitet_pct,
                    ROUND(100.0 * COUNT(snaga_w) / COUNT(*), 1) AS snaga_pct,
                    ROUND(AVG(broj_karakteristika), 1) AS prosek_popunjenih
            FROM proizvodi GROUP BY kategorija ORDER BY ukupno DESC, kategorija""",
    },
}

# redove prepisujem po 2.000 odjednom, da ne držim celu tabelu u memoriji
VELICINA_PAKETA = 2000


def prevedi_vrednost(vrednost):
    """Pretvara vrednost iz PostgreSQL-a u oblik koji SQLite čuva: Decimal u float, datum u tekst, bool u 0/1."""
    # SQLite ne zna za Decimal, datum ni pravi logički tip, pa svaki od njih prevodim u tip koji ima
    if isinstance(vrednost, decimal.Decimal):
        return float(vrednost)
    if isinstance(vrednost, (datetime.datetime, datetime.date)):
        return vrednost.isoformat()
    if isinstance(vrednost, bool):
        return int(vrednost)
    return vrednost


# -------------------------------
# PostgreSQL → SQLite
# -------------------------------
def napravi_sqlite() -> None:
    """
    Za obe baze pravi novi SQLite fajl: čita kolone svake tabele iz PostgreSQL-a,
    pravi tabelu bez primarnog ključa (da redovi ostanu redom upisa), prepisuje
    redove u paketima i na kraju pravi poglede.
    """
    # psycopg2 uvozim tek ovde, jer mi za --mysql nije potreban
    import psycopg2
    FOLDER_SQLITE.mkdir(parents=True, exist_ok=True)

    for baza, tabele in TABELE.items():
        # stari fajl brišem, da kopija uvek krene od prazne baze
        fajl = FOLDER_SQLITE / f"psz_{baza}.sqlite"
        if fajl.exists():
            fajl.unlink()
        izlaz = sqlite3.connect(fajl)
        with psycopg2.connect(dbname=NAZIVI_BAZA[baza], **ZAJEDNICKI_PARAMETRI) as ulaz:
            for tabela in tabele:
                # kolone i njihove tipove čitam iz information_schema, redom kao u tabeli
                with ulaz.cursor() as kurzor:
                    kurzor.execute("SELECT column_name, data_type FROM information_schema.columns "
                                   "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
                                   (baza, tabela))
                    kolone = kurzor.fetchall()
                opis = ", ".join(f"{ime} {TIPOVI_SQLITE[tip]}" for ime, tip in kolone)
                izlaz.execute(f"CREATE TABLE {tabela} ({opis})")

                # imenovani kurzor mi čita redove u paketima, a SELECT bez ORDER BY daje ih redom kojim su u tabeli
                broj = 0
                with ulaz.cursor(name=f"citanje_{tabela}") as kurzor:
                    kurzor.itersize = VELICINA_PAKETA
                    kurzor.execute(f"SELECT * FROM {baza}.{tabela}")
                    znakovi = ", ".join("?" for _ in kolone)
                    # u petlji uzimam paket po paket dok ne dobijem prazan, i svaku vrednost prevodim za SQLite
                    while True:
                        paket = kurzor.fetchmany(VELICINA_PAKETA)
                        if not paket:
                            break
                        izlaz.executemany(f"INSERT INTO {tabela} VALUES ({znakovi})",
                                          [tuple(prevedi_vrednost(v) for v in red) for red in paket])
                        broj += len(paket)
                print(f"[OK] {baza}.{tabela}: {broj:,} redova".replace(",", "."))

            # poglede pravim tek kad su sve tabele napunjene
            for ime, sql in POGLEDI[baza].items():
                izlaz.execute(f"CREATE VIEW {ime} AS {sql}")
        izlaz.commit()
        izlaz.close()
        print(f"[OK] {fajl} ({fajl.stat().st_size / 1e6:.1f} MB)")


# -------------------------------
# SQLite → MySQL
# -------------------------------
def mysql_je_popunjen(konekcija) -> bool:
    """Vraća True ako u MySQL-u već postoje sve tabele sa istim brojem redova kao u fajlovima."""
    # Ovom proverom preskačem ponovno učitavanje kad je MySQL već napunjen.
    with konekcija.cursor() as kurzor:
        for baza, tabele in TABELE.items():
            fajl = sqlite3.connect(f"{(FOLDER_SQLITE / f'psz_{baza}.sqlite').as_uri()}?mode=ro", uri=True)
            for tabela in tabele:
                u_fajlu = fajl.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
                # ako tabele u MySQL-u nema, upit pukne i to računam kao „nije popunjen“
                try:
                    kurzor.execute(f"SELECT COUNT(*) FROM {baza}.{tabela}")
                    u_mysql = kurzor.fetchone()[0]
                except Exception:
                    fajl.close()
                    return False
                if u_mysql != u_fajlu:
                    fajl.close()
                    return False
            fajl.close()
    return True


def tudje_tabele(kurzor, baza: str) -> list[str]:
    """
    Vraća tabele i poglede iz MySQL baze zadatog imena koje ne prepoznajem kao svoje:
    ili nisu u TABELE ni u POGLEDI, ili se imena kolona ne poklapaju sa istom tabelom
    u kopiji u fajlu. Za bazu koja ne postoji vraća praznu listu.
    """
    # information_schema.tables ima i tabele i poglede svake baze na serveru
    kurzor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (baza,))
    postojece = [red[0] for red in kurzor.fetchall()]
    moje = set(TABELE[baza]) | set(POGLEDI[baza])
    tudje = [ime for ime in postojece if ime not in moje]

    # Ime tabele mi nije dovoljan dokaz: tuđa baza se može zvati isto i imati tabelu istog
    # imena, pa za svoje tabele tražim i ista imena kolona kao u kopiji u fajlu. Kolonu
    # redni_broj ne poredim, jer je dodajem samo u MySQL-u.
    fajl = sqlite3.connect(f"{(FOLDER_SQLITE / f'psz_{baza}.sqlite').as_uri()}?mode=ro", uri=True)
    try:
        for tabela in TABELE[baza]:
            if tabela not in postojece:
                continue
            u_fajlu = {red[1].lower() for red in fajl.execute(f"PRAGMA table_info({tabela})")}
            kurzor.execute("SELECT column_name FROM information_schema.columns "
                           "WHERE table_schema = %s AND table_name = %s", (baza, tabela))
            u_mysql = {red[0].lower() for red in kurzor.fetchall()} - {"redni_broj"}
            if u_mysql != u_fajlu:
                tudje.append(tabela)
    finally:
        fajl.close()
    return sorted(tudje)


def ucitaj_u_mysql() -> None:
    """
    Pravi baze primarna i preciscena u MySQL-u i puni ih iz SQLite fajlova, a bazu u
    kojoj ima tabela koje nisu moje (po imenu ili po kolonama) ne menja. Svaka
    tabela dobija nevidljivu kolonu redni_broj kao primarni ključ, pa MySQL
    redove čita redom upisa, a SELECT * je ne prikazuje. Stariji MySQL (pre 8.0.23)
    nevidljive kolone nema, pa se tada tabela pravi bez primarnog ključa, što daje
    isti redosled. Pogled koji server ne podržava se preskače uz poruku.
    """
    pymysql = uvezi_pymysql()
    konekcija = mysql_konekcija(autocommit=True)
    try:
        # ako su sve tabele već tu sa istim brojem redova, ne učitavam ponovo
        if mysql_je_popunjen(konekcija):
            print("[INFO] Baze primarna i preciscena već su učitane u MySQL.")
            return

        with konekcija.cursor() as kurzor:
            # bazu istog imena u kojoj ima tabela koje nisu moje ne diram, da ne obrišem nečije podatke
            for baza in TABELE:
                tudje = tudje_tabele(kurzor, baza)
                if tudje:
                    raise RuntimeError(f"u MySQL-u već postoji baza '{baza}' sa tabelama koje ne "
                                       f"prepoznajem kao svoje ({', '.join(tudje)}), pa je ne menjam")
            for baza, tabele in TABELE.items():
                # fajl otvaram samo za čitanje, pa pravim bazu i u njoj brišem stare poglede
                fajl = sqlite3.connect(f"{(FOLDER_SQLITE / f'psz_{baza}.sqlite').as_uri()}?mode=ro", uri=True)
                kurzor.execute(f"CREATE DATABASE IF NOT EXISTS {baza} CHARACTER SET utf8mb4")
                kurzor.execute(f"USE {baza}")
                for ime in POGLEDI[baza]:
                    kurzor.execute(f"DROP VIEW IF EXISTS {ime}")

                for tabela in tabele:
                    pocetak = time.time()
                    # kolone i tipove čitam iz fajla (PRAGMA table_info) i prevodim ih u MySQL tipove
                    kolone = [(red[1], red[2]) for red in fajl.execute(f"PRAGMA table_info({tabela})")]
                    opis = ", ".join(f"{ime} {TIPOVI_MYSQL[tip]}" for ime, tip in kolone)
                    kurzor.execute(f"DROP TABLE IF EXISTS {tabela}")
                    # prvo probam sa nevidljivim rednim brojem, a ako server to ne zna, pravim tabelu bez njega
                    try:
                        kurzor.execute(f"CREATE TABLE {tabela} (redni_broj BIGINT NOT NULL AUTO_INCREMENT "
                                       f"PRIMARY KEY INVISIBLE, {opis}) CHARACTER SET utf8mb4")
                    except pymysql.err.ProgrammingError:
                        kurzor.execute(f"CREATE TABLE {tabela} ({opis}) CHARACTER SET utf8mb4")

                    # kolone navodim po imenu, da redni_broj popuni sam MySQL;
                    # ORDER BY rowid mi čuva redosled upisa iz fajla
                    imena = ", ".join(ime for ime, _ in kolone)
                    znakovi = ", ".join("%s" for _ in kolone)
                    upis = f"INSERT INTO {tabela} ({imena}) VALUES ({znakovi})"
                    citanje = fajl.execute(f"SELECT {imena} FROM {tabela} ORDER BY rowid")
                    broj = 0
                    while True:
                        paket = citanje.fetchmany(VELICINA_PAKETA)
                        if not paket:
                            break
                        kurzor.executemany(upis, paket)
                        broj += len(paket)
                    print(f"[OK] {baza}.{tabela}: {broj:,} redova ({time.time() - pocetak:.0f} s)".replace(",", "."))

                # pogled koji MySQL ne prihvati samo prijavim i idem dalje
                for ime, sql in POGLEDI[baza].items():
                    try:
                        kurzor.execute(f"CREATE VIEW {ime} AS {sql}")
                    except pymysql.err.MySQLError as greska:
                        print(f"[UPOZORENJE] Pogled {baza}.{ime} nije napravljen: {greska.args[-1]}")
                fajl.close()
    finally:
        # vezu zatvaram i kad nešto pukne usput
        konekcija.close()


def main() -> None:
    """Čita opcije --sqlite i --mysql i pokreće izabrani korak."""
    # obe opcije mogu zajedno; tada prvo pravim fajlove, pa ih učitavam u MySQL
    parser = argparse.ArgumentParser(description="Kopija baza u SQLite fajlovima i učitavanje u MySQL.")
    parser.add_argument("--sqlite", action="store_true", help="prepisati baze iz PostgreSQL-a u SQLite fajlove")
    parser.add_argument("--mysql", action="store_true", help="učitati SQLite fajlove u MySQL")
    argumenti = parser.parse_args()
    if argumenti.sqlite:
        napravi_sqlite()
    if argumenti.mysql:
        ucitaj_u_mysql()
    # bez ijedne opcije samo ispisujem pomoć
    if not (argumenti.sqlite or argumenti.mysql):
        parser.print_help()


if __name__ == "__main__":
    main()
