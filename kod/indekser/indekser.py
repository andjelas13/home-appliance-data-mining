#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
indekser.py — Veb indekser za proizvode bele tehnike sa winwin.rs i
gigatron.rs (Zadatak 1).

Opis:
Indekser radi u dve faze. Faza "spisak" čita sitemap fajlove prodavnice i
snima spisak adresa proizvoda; kod winwin.rs odmah zadržava samo belu tehniku,
a kod Gigatrona uzima ceo katalog, jer kategorija nije u adresi. Faza "preuzmi"
obilazi adrese sa spiska, snima stranice na disk (gzip) i svaku posetu upisuje
u primarna.dnevnik_indeksiranja. Preuzimanje sam odvojila od parsiranja, da bih
parser mogla da ponovim nad snimljenim stranicama bez novih zahteva ka sajtu.

Poštovanje pravila sajta:
- pre početka se učitava robots.txt i svaka adresa se proverava (can_fetch);
- između zahteva je pauza sa slučajnim odstupanjem;
- radi najviše 5 paralelnih radnika (podesavanja.BROJ_RADNIKA);
- neuspeo zahtev se ponavlja do BROJ_POKUSAJA puta, sa sve dužom pauzom.

Ulazi:
    sitemap fajlovi prodavnica (adrese su u podesavanja.py)

Izlazi:
    log/<prodavnica>_spisak.txt        — spisak adresa za preuzimanje
    preuzeto/<prodavnica>/*.html.gz    — snimljene stranice
    tabela primarna.dnevnik_indeksiranja

Primer poziva:
    python indekser.py --faza spisak   --prodavnica winwin
    python indekser.py --faza preuzmi  --prodavnica winwin
    python indekser.py --faza preuzmi  --prodavnica gigatron --ogranicenje 2000
    python indekser.py --faza spisak   --prodavnica sve
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import random
import re
import sys
import time
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

# folder kod/ dodajem u putanju, da bih mogla da uvezem zajednički modul za bazu
sys.path.append(str(Path(__file__).resolve().parents[1]))
from zajednicko.baza import veza, sifarnik_prodavnica
import podesavanja as pod

# -------------------------------
# Putanje i stanje koje dele niti
# -------------------------------
# foldere za stranice i spiskove pravim odmah pri učitavanju, ako već ne postoje
KOREN       = Path(__file__).resolve().parent
FOLDER_HTML = KOREN / pod.FOLDER_HTML
FOLDER_LOG  = KOREN / pod.FOLDER_LOG
FOLDER_HTML.mkdir(parents=True, exist_ok=True)
FOLDER_LOG.mkdir(parents=True, exist_ok=True)

# brojače i dnevnik menja više niti odjednom, pa ih diram samo pod katancem
KATANAC   = threading.Lock()
BROJACI   = {"uspesno": 0, "greska": 0, "preskoceno": 0}
DNEVNIK   = []          # ovde skupljam redove dok ih paketno ne upišem u primarna.dnevnik_indeksiranja


# -------------------------------
# Pomoćne funkcije
# -------------------------------
def ime_fajla(url: str) -> str:
    """
    Pravi ime fajla od SHA-1 sažetka adrese i dodaje nastavak .html.gz.
    Ista adresa uvek dobije isto ime, a ime nije predugačko kao sama adresa.
    """
    # adresa ima kose crte i znakove koji ne smeju u ime fajla, pa uzimam njen heš
    return hashlib.sha1(url.encode("utf-8")).hexdigest() + ".html.gz"


def pauza() -> None:
    """Čeka PAUZA_SEKUNDI ± PAUZA_ODSTUPANJE (najmanje 0,1 s), da se server prodavnice ne opterećuje."""
    # max sa 0.1 mi čuva da pauza nikad ne ispadne negativna ili nula
    time.sleep(max(0.1, pod.PAUZA_SEKUNDI + random.uniform(-pod.PAUZA_ODSTUPANJE,
                                                            pod.PAUZA_ODSTUPANJE)))


def ucitaj_robots(osnovni_url: str) -> RobotFileParser:
    """
    Preuzima robots.txt sa istim zaglavljima kao ostale stranice i vraća pravila;
    ako fajl nije dostupan, sve je dozvoljeno. Ne koristim RobotFileParser.read(),
    jer on šalje Python User-Agent, prodavnica to odbije sa HTTP 403, a biblioteka
    tada zabrani sve adrese.
    """
    adresa = osnovni_url.rstrip("/") + "/robots.txt"
    pravila = RobotFileParser()
    pravila.set_url(adresa)
    # fajl sama preuzimam i tekst dajem u parse(); kad ga nema, parse([]) mi znači da nema zabrana
    try:
        odgovor = requests.get(adresa, headers=pod.ZAGLAVLJA, timeout=pod.VREME_CEKANJA)
        if odgovor.status_code == 200 and odgovor.text.strip():
            pravila.parse(odgovor.text.splitlines())
            # Disallow redove brojim samo da bih ispisala koliko zabrana ima
            broj_pravila = len(re.findall(r"(?im)^\s*disallow\s*:", odgovor.text))
            print(f"[INFO] robots.txt učitan sa {osnovni_url} ({broj_pravila} zabrana)")
        else:
            pravila.parse([])
            print(f"[INFO] robots.txt nije dostupan (HTTP {odgovor.status_code}) — bez dodatnih zabrana")
    except Exception as greska:
        pravila.parse([])
        print(f"[INFO] robots.txt nije dostupan ({greska}) — bez dodatnih zabrana")
    return pravila


def preuzmi_xml(url: str) -> ET.Element | None:
    """Preuzima jedan sitemap fajl i vraća koren XML stabla, ili None ako preuzimanje ili parsiranje ne uspe."""
    # raise_for_status mi pretvara loš HTTP status u izuzetak, pa sve greške hvatam na jednom mestu
    try:
        odgovor = requests.get(url, headers=pod.ZAGLAVLJA, timeout=pod.VREME_CEKANJA)
        odgovor.raise_for_status()
        return ET.fromstring(odgovor.content)
    except Exception as greska:
        print(f"[GRESKA] Sitemap {url}: {greska}")
        return None


def adrese_iz_sitemapa(koren: ET.Element) -> list[str]:
    """
    Vraća tekst svih <loc> elemenata, i iz običnog sitemap-a i iz sitemap indeksa.
    Poredim samo kraj naziva oznake, jer ElementTree ispred naziva dodaje namespace.
    """
    # iter() mi prolazi kroz celo stablo, pa ne moram da znam dubinu na kojoj je <loc>
    return [element.text.strip()
            for element in koren.iter()
            if element.tag.endswith("loc") and element.text]


# -------------------------------
# Faza 1: pravljenje spiska adresa
# -------------------------------
def zanimljiva_magento_adresa(url: str) -> bool:
    """
    Proverava da li adresa sa winwin.rs pripada beloj tehnici, na osnovu
    kategorija koje su upisane u samu putanju, npr.:
        /bela-tehnika/frizideri/kombinovani-frizideri/gorenje-nrk61jsy2w
         ^prvi nivo   ^drugi nivo
    """
    # putanju delim po kosoj crti; adresa sa manje od dva dela nije stranica proizvoda
    putanja = urlparse(url).path.strip("/").split("/")
    if len(putanja) < 2:
        return False

    # prvi nivo mora biti u KATEGORIJE_MAGENTO sa vrednošću True
    prvi_nivo = putanja[0]
    if not pod.KATEGORIJE_MAGENTO.get(prvi_nivo, False):
        return False

    # iz 'tv-foto-audio-i-video' puštam samo drugi nivo 'televizori'
    if prvi_nivo == "tv-foto-audio-i-video" and putanja[1] not in pod.PODKATEGORIJE_TV:
        return False

    # sve nivoe ispod prvog proveravam zbog dodatne opreme, rezervnih delova i potrošnog
    # materijala, jer oprema ume da bude i na drugom nivou adrese
    if any(deo in pod.ISKLJUCENE_PODKATEGORIJE for deo in putanja[1:]):
        return False

    return True


def napravi_spisak(sifra: str) -> Path:
    """
    Funkcija čita sitemap fajlove prodavnice, kod winwin.rs zadržava samo adrese
    bele tehnike, izbacuje duplikate, meša spisak i snima ga u log/<sifra>_spisak.txt.
    Vraća putanju do snimljenog spiska.
    """
    podaci = pod.PRODAVNICE[sifra]
    print(f"[INFO] Pravim spisak adresa za '{podaci['naziv']}' ({podaci['osnovni_url']})")

    # Gigatron ima sitemap indeks, pa iz njega prvo čitam adrese pojedinačnih sitemap
    # fajlova; za winwin.rs sam spisak sitemap fajlova upisala u podešavanja
    if "sitemap_indeks" in podaci:
        koren = preuzmi_xml(podaci["sitemap_indeks"])
        spisak_sitemapova = adrese_iz_sitemapa(koren) if koren is not None else []
        print(f"[INFO] Sitemap indeks sadrži {len(spisak_sitemapova)} fajlova")
    else:
        spisak_sitemapova = podaci["sitemap"]

    # u ovoj petlji skidam sitemap po sitemap i skupljam sve <loc> adrese; sitemap koji
    # ne uspe da se preuzme preskačem, a posle svakog pravim pauzu
    adrese = []
    for redni_broj, adresa_sitemapa in enumerate(spisak_sitemapova, start=1):
        koren = preuzmi_xml(adresa_sitemapa)
        if koren is None:
            continue
        nove = adrese_iz_sitemapa(koren)
        adrese.extend(nove)
        print(f"[INFO]   ({redni_broj}/{len(spisak_sitemapova)}) {adresa_sitemapa} → {len(nove):,} adresa")
        pauza()

    # broj pre filtriranja pamtim samo za završni ispis
    ukupno_sirovo = len(adrese)

    # belu tehniku ovde filtriram samo za winwin.rs, jer je kategorija u adresi;
    # Gigatron filtriram tek u parseru, po putanji kategorije iz JSON-LD-a
    if podaci["parser"] == "magento":
        adrese = [u for u in adrese if zanimljiva_magento_adresa(u)]

    # set izbacuje duplikate, a sortiram pre mešanja jer redosled u set-u nije isti pri
    # svakom pokretanju; mešanje sa fiksnim semenom daje ponovljiv spisak, pa i prekinuto
    # preuzimanje ima stranice iz svih kategorija
    adrese = sorted(set(adrese))
    random.Random(pod.SEME_MESANJA).shuffle(adrese)

    # spisak snimam kao običan tekst, jedna adresa u redu, da ga faza "preuzmi" pročita
    putanja_spiska = FOLDER_LOG / f"{sifra}_spisak.txt"
    putanja_spiska.write_text("\n".join(adrese), encoding="utf-8")

    print(f"[OK] {podaci['naziv']}: {ukupno_sirovo:,} adresa iz sitemapa "
          f"→ {len(adrese):,} zadržano → {putanja_spiska}")
    return putanja_spiska


# -------------------------------
# Faza 2: preuzimanje stranica
# -------------------------------
def preuzmi_stranicu(url: str, sifra: str, prodavnica_id: int,
                     pravila: RobotFileParser, sesija: requests.Session) -> None:
    """
    Preuzima jednu stranicu (do BROJ_POKUSAJA pokušaja), snima je kao gzip i
    dodaje red u DNEVNIK. Stranicu koja je već na disku ili je zabranjena u
    robots.txt preskače.
    """
    # ime fajla pravim od heša adrese, pa odmah znam gde bi stranica bila na disku
    odredisni_folder = FOLDER_HTML / sifra
    odrediste = odredisni_folder / ime_fajla(url)

    # fajl već postoji i nije prazan, znači da je stranica preuzeta u prethodnom
    # pokretanju; tako prekinuto preuzimanje mogu da nastavim
    if odrediste.exists() and odrediste.stat().st_size > 0:
        with KATANAC:
            BROJACI["preskoceno"] += 1
        return

    # adresu koju robots.txt zabranjuje ne preuzimam, samo je beležim u dnevnik
    if not pravila.can_fetch(pod.ZAGLAVLJA["User-Agent"], url):
        with KATANAC:
            BROJACI["preskoceno"] += 1
            DNEVNIK.append((prodavnica_id, url, None, False, "robots.txt zabranjuje", 0))
        return

    # vreme merim od prvog pokušaja, pa trajanje uključuje i pauze između ponavljanja
    pocetak = time.perf_counter()
    poslednja_greska, status = None, None

    # posle neuspelog pokušaja pauza raste: PAUZA_POSLE_GRESKE puta redni broj pokušaja
    for pokusaj in range(1, pod.BROJ_POKUSAJA + 1):
        try:
            odgovor = sesija.get(url, headers=pod.ZAGLAVLJA, timeout=pod.VREME_CEKANJA)
            status = odgovor.status_code

            # uspeh: snimam sadržaj kao gzip i beležim trajanje u milisekundama
            if status == 200:
                odrediste.write_bytes(gzip.compress(odgovor.content))
                trajanje = int((time.perf_counter() - pocetak) * 1000)
                with KATANAC:
                    BROJACI["uspesno"] += 1
                    DNEVNIK.append((prodavnica_id, url, status, True, None, trajanje))
                pauza()
                return

            # 404 znači da proizvoda više nema na sajtu, pa ponavljanje nema smisla
            if status == 404:
                poslednja_greska = "HTTP 404 (stranica ne postoji)"
                break

            poslednja_greska = f"HTTP {status}"
        except Exception as greska:
            # tekst greške skraćujem na 200 znakova, da stane u kolonu poruka_greske
            poslednja_greska = str(greska)[:200]

        if pokusaj < pod.BROJ_POKUSAJA:
            time.sleep(pod.PAUZA_POSLE_GRESKE * pokusaj)

    # ovde stignem kad nijedan pokušaj nije uspeo ili je server vratio 404,
    # pa u dnevnik upisujem poslednju grešku
    trajanje = int((time.perf_counter() - pocetak) * 1000)
    with KATANAC:
        BROJACI["greska"] += 1
        DNEVNIK.append((prodavnica_id, url, status, False, poslednja_greska, trajanje))
    pauza()


def upisi_dnevnik() -> None:
    """
    Pod katancem uzima sve redove iz DNEVNIK i prazni listu, pa ih jednim
    executemany pozivom upisuje u primarna.dnevnik_indeksiranja.
    """
    # kopiju pravim pod katancem, a sam upis u bazu radim van njega, da niti ne čekaju bazu
    with KATANAC:
        redovi, DNEVNIK[:] = list(DNEVNIK), []
    if not redovi:
        return
    with veza("primarna") as konekcija:
        with konekcija.cursor() as kurzor:
            kurzor.executemany(
                """INSERT INTO primarna.dnevnik_indeksiranja
                       (prodavnica_id, url, http_status, uspesno, poruka_greske, trajanje_ms)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                redovi,
            )


def preuzmi_sve(sifra: str, ogranicenje: int | None) -> None:
    """
    Čita spisak adresa prodavnice (po potrebi samo prvih `ogranicenje`), učitava
    robots.txt i preuzima stranice u BROJ_RADNIKA niti. Na svakih 250 adresa
    upisuje dnevnik u bazu i ispisuje tempo i procenu preostalog vremena.
    """
    # bez spiska iz faze "spisak" nemam šta da preuzimam, pa samo javim i izađem
    podaci = pod.PRODAVNICE[sifra]
    putanja_spiska = FOLDER_LOG / f"{sifra}_spisak.txt"
    if not putanja_spiska.exists():
        print(f"[GRESKA] Ne postoji {putanja_spiska}. Prvo pokreni fazu 'spisak'.")
        return

    # prazne redove izbacujem, a sa --ogranicenje uzimam samo početak spiska za probu
    adrese = [red.strip() for red in putanja_spiska.read_text(encoding="utf-8").splitlines() if red.strip()]
    if ogranicenje:
        adrese = adrese[:ogranicenje]

    # robots.txt i id prodavnice iz baze učitavam jednom, pre nego što krenu niti
    (FOLDER_HTML / sifra).mkdir(parents=True, exist_ok=True)
    pravila = ucitaj_robots(podaci["osnovni_url"])
    prodavnica_id = sifarnik_prodavnica()[sifra]

    print(f"[INFO] Preuzimam {len(adrese):,} adresa sa {podaci['naziv']} "
          f"({pod.BROJ_RADNIKA} radnika, pauza ~{pod.PAUZA_SEKUNDI}s)")
    pocetak = time.perf_counter()

    # jedna sesija za sve radnike, da se otvorene veze ka serveru ponovo koriste;
    # map vraća rezultate redom, pa mi redni_broj pokazuje koliko je adresa obrađeno
    sesija = requests.Session()
    with ThreadPoolExecutor(max_workers=pod.BROJ_RADNIKA) as izvrsilac:
        for redni_broj, _ in enumerate(
            izvrsilac.map(lambda u: preuzmi_stranicu(u, sifra, prodavnica_id, pravila, sesija), adrese),
            start=1,
        ):
            # na svakih 250 adresa upisujem dnevnik u bazu i ispisujem napredak;
            # preostalo vreme računam kao broj preostalih adresa podeljen tempom
            if redni_broj % 250 == 0:
                upisi_dnevnik()
                proteklo = time.perf_counter() - pocetak
                tempo = redni_broj / proteklo if proteklo else 0
                preostalo = (len(adrese) - redni_broj) / tempo / 60 if tempo else 0
                print(f"[INFO] {redni_broj:,}/{len(adrese):,}  "
                      f"uspešno={BROJACI['uspesno']:,} greška={BROJACI['greska']:,} "
                      f"preskočeno={BROJACI['preskoceno']:,}  "
                      f"tempo={tempo:.1f} str/s  preostalo≈{preostalo:.0f} min")

    # posle petlje upisujem ostatak dnevnika koji nije dostigao punih 250
    upisi_dnevnik()
    minuti = (time.perf_counter() - pocetak) / 60
    print(f"[OK] {podaci['naziv']}: uspešno={BROJACI['uspesno']:,} "
          f"greška={BROJACI['greska']:,} preskočeno={BROJACI['preskoceno']:,} "
          f"za {minuti:.1f} min → {FOLDER_HTML / sifra}")


# -------------------------------
# Glavni program
# -------------------------------
def main() -> None:
    """Čita argumente komandne linije i za svaku izabranu prodavnicu pokreće fazu spisak ili preuzmi."""
    # --faza je obavezna, a bez --prodavnica obrađujem obe prodavnice
    parser = argparse.ArgumentParser(description="Veb indekser za proizvode bele tehnike.")
    parser.add_argument("--faza", choices=["spisak", "preuzmi"], required=True,
                        help="'spisak' pravi listu adresa iz sitemapa, 'preuzmi' skida stranice")
    parser.add_argument("--prodavnica", default="sve",
                        help="šifra prodavnice (winwin ili gigatron) ili 'sve'")
    parser.add_argument("--ogranicenje", type=int, default=None,
                        help="maksimalan broj adresa za preuzimanje (za probu)")
    argumenti = parser.parse_args()

    # 'sve' mi daje sve šifre iz PRODAVNICE, a nepoznatu šifru odbijam sa spiskom dostupnih
    if argumenti.prodavnica == "sve":
        sifre = list(pod.PRODAVNICE.keys())
    elif argumenti.prodavnica in pod.PRODAVNICE:
        sifre = [argumenti.prodavnica]
    else:
        print(f"[GRESKA] Nepoznata prodavnica '{argumenti.prodavnica}'. "
              f"Dostupne: {', '.join(pod.PRODAVNICE)}")
        return

    for sifra in sifre:
        if argumenti.faza == "spisak":
            napravi_spisak(sifra)
        else:
            # brojače vraćam na nulu za svaku prodavnicu, da se ispisi ne sabiraju
            BROJACI.update({"uspesno": 0, "greska": 0, "preskoceno": 0})
            preuzmi_sve(sifra, argumenti.ogranicenje)


if __name__ == "__main__":
    main()
