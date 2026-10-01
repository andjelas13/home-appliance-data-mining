#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser_magento.py — Veb parser za winwin.rs, prodavnicu na Magento platformi
                    (Zadatak 1).

Opis:
Iz snimljene stranice proizvoda izdvaja podatke za primarnu bazu, kombinacijom
tri tehnike, jer nijedna sama ne pokriva sve. DOM parserom (BeautifulSoup) čita
naziv, šifru i karakteristike iz tabele (th.label / td.data) i iz liste detalja
(li sa tri span elementa), a stanje zaliha iz vidljivog bloka dostupnosti
(div.main_stock_status). Cenu i valutu čita iz meta oznaka product:price:*,
jer tu cena piše bez tačaka, razmaka i oznake dinara. Regularnim izrazom nad
JavaScript objektom dataLayer uzima šifru, naziv, brend i punu putanju kategorije.

Poznata neuređenost izvora (rešava se u Zadatku 2):
- stranica ume da ima dve tabele (uvoznikovu i proizvođačevu), pa isti atribut
  dođe dva puta sa različitim vrednostima (npr. "Visina" 187 cm i 185 cm);
  ovde se upisuju obe;
- u dataLayer-u (polje dimension10) Winwin za svaki proizvod piše „Out of stock“,
  pa to polje ne čitam, nego zalihe uzimam iz bloka koji kupac vidi na strani.
Red "Import Specifikacija" je slepljen tekst ostalih redova, pa ga preskačem
već ovde.

Ulazi:
    preuzeto/<prodavnica>/*.html.gz   — stranice koje je snimio indekser

Izlazi:
    rečnik sa podacima o proizvodu i listom karakteristika
    (upis u bazu radi skripta upis_u_bazu.py)

Primer poziva (samostalna proba nad jednim fajlom):
    python parser_magento.py --fajl ../indekser/preuzeto/winwin/abc123.html.gz
"""

from __future__ import annotations

import argparse
import gzip
from html import unescape
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# podešavanja su u folderu indeksera, pa taj folder dodajem u putanju za uvoz
sys.path.append(str(Path(__file__).resolve().parents[1] / "indekser"))
import podesavanja as pod

# -------------------------------
# Regularni izrazi
# -------------------------------
# ovim obrascem hvatam zapis proizvoda u dataLayer-u; polja idu ovim redom:
# {"id":"1101728","name":"...","price":45999,"brand":"GORENJE",
#  "category":"Bela tehnika\/Frižideri\/...","dimension10":"Out of stock"}
# polje dimension10 ne hvatam, jer u njemu za svaki proizvod piše "Out of stock"
# deo (?:[^"\\]|\\.)* sam napisala da naziv sa navodnikom ispred kog je \ ne preseče tekst
DATALAYER_RE = re.compile(
    r'"id"\s*:\s*"(?P<id>[^"]*)"\s*,\s*'
    r'"name"\s*:\s*"(?P<naziv>(?:[^"\\]|\\.)*)"\s*,\s*'
    r'"price"\s*:\s*(?P<cena>[0-9.]+)\s*,\s*'
    r'"brand"\s*:\s*"(?P<brend>(?:[^"\\]|\\.)*)"\s*,\s*'
    r'"category"\s*:\s*"(?P<kategorija>(?:[^"\\]|\\.)*)"'
)

# njime tražim prvi broj u tekstu, sa znakom minus i decimalama posle tačke ili zareza
BROJ_RE = re.compile(r"-?\d+(?:[.,]\d+)?")

# nazivi redova koje ne smatram karakteristikom uređaja, jer su slepljen tekst ostalih redova ili opis
PRESKOCI_ATRIBUTE = {"import specifikacija", "specifikacija", "opis"}


# -------------------------------
# Pomoćne funkcije
# -------------------------------
def procitaj_html(putanja: Path) -> str:
    """Otvara snimljeni .html.gz fajl, raspakuje ga i vraća HTML kao tekst."""
    # errors="ignore" stavljam da me jedan pokvaren bajt ne zaustavi na celoj stranici
    return gzip.decompress(Path(putanja).read_bytes()).decode("utf-8", errors="ignore")


def ocisti(tekst: str | None) -> str | None:
    """Menja nizove razmaka jednim razmakom, skida razmake sa krajeva i za prazan tekst vraća None."""
    # prazan tekst mi postaje None, da u bazu ide NULL, a ne prazan string
    if tekst is None:
        return None
    tekst = re.sub(r"\s+", " ", tekst).strip()
    return tekst or None


def raspakuj_json_tekst(tekst: str) -> str:
    """
    Tekst iz JavaScript stringa pretvara u običan tekst (npr. \\/ → /) tako što ga
    čita kao JSON string. Ako to ne uspe, ručno menja samo \\/ i \\".
    Na kraju HTML entitete vraća u slova (&Scaron; → Š, K&ouml;rting → Körting).
    """
    # tekst oko sebe dobije navodnike, pa ga json.loads čita kao jedan JSON string
    try:
        tekst = json.loads(f'"{tekst}"')
    except Exception:
        tekst = tekst.replace("\\/", "/").replace('\\"', '"')
    # u dataLayer-u su neka slova zapisana kao HTML entiteti, pa ih unescape vraća u slova
    return unescape(tekst)


def sadrzaj_mete(supa: BeautifulSoup, svojstvo: str) -> str | None:
    """Traži <meta property="..."> sa zadatim svojstvom i vraća njen content, ili None."""
    # ovu pomoćnu koristim i za og:title i za product:price:amount/currency
    oznaka = supa.find("meta", attrs={"property": svojstvo})
    return oznaka.get("content") if oznaka else None


def stanje_zaliha(supa: BeautifulSoup) -> tuple[str | None, bool | None]:
    """
    Čita blok dostupnosti koji kupac vidi na strani:
    <div class="main_stock_status"><div class="stock available">...Dostupno odmah...
    Vraća par (tekst sa strane, na_stanju): klasa available daje True, klasa
    unavailable daje False, a bez bloka vraća (None, None).
    """
    # isti ishod daje i JSON-LD oznaka InStock, ali nju Winwin stavlja samo kad je proizvod dostupan
    blok = supa.select_one(".main_stock_status .stock")
    if not blok:
        return None, None
    tekst = ocisti(blok.get_text(" "))
    # class je u BeautifulSoup-u lista, pa proveravam da li je u njoj tačno reč available
    klase = blok.get("class") or []
    if "available" in klase:
        return tekst, True
    if "unavailable" in klase:
        return tekst, False
    return tekst, None


def u_broj(tekst: str | None) -> float | None:
    """
    Briše tačke, zarez menja tačkom i vraća prvi broj kao float
    ('45.999,00 RSD' → 45999.0). Tačka se čita kao razdvajanje hiljada.
    """
    # prvo sklanjam tačke hiljada, pa zarez postaje decimalna tačka, tek onda tražim broj
    if not tekst:
        return None
    tekst = tekst.replace(".", "").replace(",", ".")
    nadjeno = BROJ_RE.search(tekst)
    return float(nadjeno.group(0)) if nadjeno else None


# -------------------------------
# Izdvajanje karakteristika
# -------------------------------
def karakteristike_iz_tabele(supa: BeautifulSoup) -> list[tuple[str, str]]:
    """
    Vraća parove (naziv, vrednost) iz redova tabele koji imaju th.label i td.data.
    Redove iz PRESKOCI_ATRIBUTE izbacuje, a praznu vrednost upisuje kao prazan tekst.
    """
    # prolazim kroz sve redove tabele; red bez th.label ili td.data nije red specifikacije
    stavke = []
    for red in supa.select("tr"):
        zaglavlje = red.find("th", class_="label")
        vrednost = red.find("td", class_="data")
        if not zaglavlje or not vrednost:
            continue
        # get_text(" ") mi stavlja razmak između delova teksta, da se reči ne slepe
        naziv = ocisti(zaglavlje.get_text(" "))
        if not naziv or naziv.lower() in PRESKOCI_ATRIBUTE:
            continue
        stavke.append((naziv, ocisti(vrednost.get_text(" ")) or ""))
    return stavke


def karakteristike_iz_liste(supa: BeautifulSoup) -> list[tuple[str, str]]:
    """
    Čita listu detalja proizvoda, gde stavka ima tačno tri span elementa:
    <li><span>Naziv</span><span></span><span>Vrednost</span></li>.
    Uzima naziv iz prvog i vrednost iz trećeg; nepotpune stavke preskače.
    """
    # recursive=False mi daje samo span elemente direktno u li, a ne one ugnežđene dublje
    stavke = []
    for stavka in supa.select("li"):
        rasponi = stavka.find_all("span", recursive=False)
        if len(rasponi) != 3:
            continue
        # srednji span je prazan razdvajač, pa ga ne čitam
        naziv = ocisti(rasponi[0].get_text(" "))
        vrednost = ocisti(rasponi[2].get_text(" "))
        if not naziv or not vrednost or naziv.lower() in PRESKOCI_ATRIBUTE:
            continue
        stavke.append((naziv, vrednost))
    return stavke


# -------------------------------
# Glavna funkcija parsiranja
# -------------------------------
def parsiraj(html: str) -> dict | None:
    """
    Parsira jednu stranicu sa winwin.rs i vraća rečnik sa podacima o proizvodu.
    Vraća None ako se ne nađe adresa ili naziv, jer to onda nije stranica proizvoda,
    i kad je adresa u podkategoriji opreme (ISKLJUCENE_PODKATEGORIJE).
    """
    # HTML jednom pretvaram u DOM stablo (lxml parser); samo dataLayer (JavaScript kod)
    # tražim direktno u sirovom HTML-u
    supa = BeautifulSoup(html, "lxml")

    # 1) adresu uzimam iz kanonske oznake stranice
    kanonska = supa.find("link", rel="canonical")
    url = kanonska.get("href") if kanonska else None
    if not url:
        return None
    # opremu i delove ne upisujem, na kom god nivou adrese da stoji podkategorija
    if any(deo in pod.ISKLJUCENE_PODKATEGORIJE for deo in urlparse(url).path.strip("/").split("/")):
        return None

    # 2) šifru, naziv, brend i kategoriju uzimam iz dataLayer-a; ako zapisa nema, sve je None
    pogodak = DATALAYER_RE.search(html)
    if pogodak:
        sku = ocisti(pogodak.group("id"))
        naziv_dl = ocisti(raspakuj_json_tekst(pogodak.group("naziv")))
        brend = ocisti(raspakuj_json_tekst(pogodak.group("brend")))
        kategorija_puna = ocisti(raspakuj_json_tekst(pogodak.group("kategorija")))
    else:
        sku = naziv_dl = brend = kategorija_puna = None

    # 3) naziv tražim redom u dataLayer-u, og:title oznaci i naslovu h1
    naziv = naziv_dl or ocisti(sadrzaj_mete(supa, "og:title"))
    if not naziv and supa.h1:
        naziv = ocisti(supa.h1.get_text(" "))
    if not naziv:
        return None

    # 4) šifru čitam iz vidljivog dela stranice samo ako je nema u dataLayer-u
    if not sku:
        blok = supa.select_one(".product.attribute.sku .value")
        sku = ocisti(blok.get_text()) if blok else None

    # 5) cena i valuta iz meta oznaka; kad oznake valute nema, pišem RSD
    cena = u_broj(sadrzaj_mete(supa, "product:price:amount"))
    valuta = ocisti(sadrzaj_mete(supa, "product:price:currency")) or "RSD"

    # 6) kategorija mi je poslednji nivo pune putanje ("Kombinovani frižideri"),
    # a bez putanje drugi deo adrese ("frizideri")
    if kategorija_puna:
        kategorija = kategorija_puna.split("/")[-1].strip()
    else:
        delovi = [d for d in url.split("winwin.rs/")[-1].split("/") if d]
        kategorija = delovi[1] if len(delovi) > 2 else None

    # 7) zalihe čitam iz bloka dostupnosti: tekst („Dostupno odmah“, „Dostupno na lageru
    # dobavljača“, „Proizvod trenutno nije dostupan“) ide u dostupnost, a klasa bloka u na_stanju
    dostupnost, na_stanju = stanje_zaliha(supa)

    # 8) opis uzimam iz meta oznake description
    opis_oznaka = supa.find("meta", attrs={"name": "description"})
    opis = ocisti(opis_oznaka.get("content")) if opis_oznaka else None

    # 9) karakteristike spajam iz tabele i iz liste, a isti par naziv–vrednost
    # (bez obzira na velika i mala slova) pamtim u skupu videno i ne ponavljam ga
    karakteristike, videno = [], set()
    for naziv_atributa, vrednost in karakteristike_iz_tabele(supa) + karakteristike_iz_liste(supa):
        kljuc = (naziv_atributa.lower(), vrednost.lower())
        if kljuc in videno:
            continue
        videno.add(kljuc)
        karakteristike.append((naziv_atributa, vrednost))

    # ključevi rečnika su isti kao kod parsera za Gigatron, da upis_u_bazu.py radi sa oba
    return {
        "url":             url,
        "sku":             sku,
        "naziv":           naziv,
        "brend":           brend,
        "kategorija_puna": kategorija_puna,
        "kategorija":      kategorija,
        "cena":            cena,
        "valuta":          valuta,
        "dostupnost":      dostupnost,
        "na_stanju":       na_stanju,
        "ocena":           None,          # winwin.rs ne prikazuje ocene kupaca, pa ovde stavljam None
        "broj_ocena":      None,
        "opis":            opis,
        "karakteristike":  karakteristike,
    }


# -------------------------------
# Samostalna proba nad jednim fajlom
# -------------------------------
def main() -> None:
    """Proba parsera: čita fajl zadat sa --fajl, parsira ga i ispisuje svako polje."""
    # ovu probu pokrećem ručno nad jednim fajlom, bez baze, da vidim šta parser izvuče
    parser = argparse.ArgumentParser(description="Proba Magento parsera nad jednom snimljenom stranicom.")
    parser.add_argument("--fajl", required=True, help="putanja do .html.gz fajla")
    argumenti = parser.parse_args()

    podaci = parsiraj(procitaj_html(Path(argumenti.fajl)))
    if not podaci:
        print("[GRESKA] Stranica nije prepoznata kao proizvod.")
        return

    # karakteristike ispisujem svaku u svom redu, a vrednost skraćujem na 60 znakova
    for kljuc, vrednost in podaci.items():
        if kljuc == "karakteristike":
            print(f"[INFO] karakteristike ({len(vrednost)}):")
            for naziv, vred in vrednost:
                print(f"         {naziv:35} = {vred[:60]}")
        else:
            print(f"[INFO] {kljuc:16} = {vrednost}")


if __name__ == "__main__":
    main()
