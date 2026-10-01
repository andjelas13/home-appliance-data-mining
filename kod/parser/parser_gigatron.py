#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser_gigatron.py — Veb parser za gigatron.rs (Zadatak 1).

Opis:
Gigatron je napravljen na Next.js-u, pa ovde koristim drugačiju tehniku nego za
winwin.rs: čitanje semantičkih anotacija (JSON-LD po schema.org rečniku). Iz
bloka "Product" se čitaju naziv, šifra, brend, cena, valuta, dostupnost i ocena,
a iz bloka "BreadcrumbList" putanja kategorije. Karakteristike se čitaju iz HTML
tabele ili, kod novijeg izgleda stranice, iz JSON zapisa u HTML-u, a energetska
klasa iz alt atributa slike nalepnice. Adresa proizvoda nema kategoriju, pa se
bela tehnika izdvaja tek ovde, po putanji iz BreadcrumbList bloka.

Ulazi:
    preuzeto/gigatron/*.html.gz

Izlazi:
    rečnik sa podacima o proizvodu i listom karakteristika
    (upis u bazu radi upis_u_bazu.py)

Primer poziva (proba nad jednim snimljenim fajlom):
    python parser_gigatron.py --fajl ../indekser/preuzeto/gigatron/abc123.html.gz
    python parser_gigatron.py --fajl ../indekser/preuzeto/gigatron/abc123.html.gz --sve_kategorije
"""

from __future__ import annotations

import argparse
import gzip
from html import unescape
import json
import re
import sys
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

# podešavanja su u folderu indeksera, pa taj folder dodajem u putanju za uvoz
sys.path.append(str(Path(__file__).resolve().parents[1] / "indekser"))
import podesavanja as pod

# -------------------------------
# Regularni izrazi i konstante
# -------------------------------
# ovim hvatam karakteristiku iz JSON zapisa novijeg izgleda stranice: "name", pa najviše
# 140 znakova dalje "values", npr. {\"name\":\"Broj obrtaja centrifuge\",\"values\":[\"1200 obr/min\"]};
# navodnici umeju da imaju obrnutu kosu crtu ispred, pa sam obrazac napisala da prihvata oba oblika;
# iz niza čitam najviše 400 znakova, pa mi duge slobodne napomene i najduži spiskovi funkcija
# (oko 1.960 redova) ne ulaze u karakteristike
PAYLOAD_KARAKTERISTIKA_RE = re.compile(
    r'\\?"name\\?"\s*:\s*\\?"(?P<naziv>[^"\\]{2,80})\\?"'
    r'.{0,140}?'
    r'\\?"values\\?"\s*:\s*\[(?P<vrednosti>[^\]]{0,400})\]'
)
# a ovim izdvajam jednu vrednost u navodnicima iz niza "values"; koristim ga samo kao
# rezervu kad niz ne može da se pročita kao JSON (vrednosti_iz_niza)
VREDNOST_RE = re.compile(r'\\?"([^"\\]{1,200})\\?"')
# HTML oznaka unutar vrednosti, npr. <p>150 mm</p> ili <br />; posle < mora da ide slovo
# ili kosa crta, pa tekst "standby < 0,5 W" ne diram
OZNAKA_RE = re.compile(r"</?[a-zA-Z][^>]*>")

# u istom JSON zapisu su i unutrašnja polja prodavnice (slike nalepnice, cene za
# lojalnost, garancija, zastavice is_/has_, polja iz poslovnog programa sa prefiksom NAV,
# sellerId, oznaka i opis outlet artikla); to nisu osobine uređaja, pa ih izbacujem po
# nazivu, da mi ne bi lažno povećale broj karakteristika pri proveri potpunosti u Zadatku 2;
# zemlju porekla (Country of origin) i uvoznika (Vendor) zadržavam, jer su to podaci o samom
# proizvodu, isti kao „Zemlja porekla“ i „Uvoznik“ na winwin stranama
UNUTRASNJA_POLJA_RE = re.compile(
    r"image|file|warranty|loyalty|price|url|slug|media|banner|icon|badge"
    r"|\bid\b|\bsku\b|date|online kupovina|^18\+$|^is[ _]|^has[ _]"
    r"|^NAV\b|^sellerId$|^Outlet$|^Show In Large Category$|^Long Description$",
    re.IGNORECASE,
)
# vrednost koja je heš ime fajla, počinje sa /media/ ili se završava na .jpg/.png/.pdf/.webp
# ne smatram podatkom o uređaju; isto važi za oznaku oblika $51, koja je samo
# pokazivač na drugi deo zapisa stranice, a ne sam tekst
TEHNICKA_VREDNOST_RE = re.compile(r"^[0-9a-f]{16,}\.\w+$|^/media/|\.(jpg|png|pdf|webp)$|^\$[0-9a-f]+$",
                                  re.IGNORECASE)

# alt="Energetska oznaka - F - Novo"  →  klasa 'F' (A–G, do tri plusa), skala 'Novo';
# skala je u drugoj grupi, koja nije obavezna
ENERGETSKA_RE = re.compile(r"Energetska\s+oznaka\s*-\s*([A-G]\+{0,3})\s*(?:-\s*(.+))?", re.IGNORECASE)

# schema.org dostupnost prevodim u na_stanju: True ili False, a None za preorder i backorder,
# jer tada ne znam da li je uređaj na stanju; ključeve sam pisala malim slovima, kao i oznaku
# sa stranice posle .lower()
DOSTUPNOST = {
    "instock":        True,
    "instoreonly":    True,
    "limitedavailability": True,
    "outofstock":     False,
    "soldout":        False,
    "discontinued":   False,
    "preorder":       None,
    "backorder":      None,
}


# -------------------------------
# Pomoćne funkcije
# -------------------------------
def procitaj_html(putanja: Path) -> str:
    """Učitava .html.gz fajl sa diska, raspakuje ga i vraća HTML kao tekst (neispravne bajtove preskače)."""
    # indekser je stranicu snimio kao gzip, pa je ovde samo raspakujem i dekodiram
    return gzip.decompress(Path(putanja).read_bytes()).decode("utf-8", errors="ignore")


def ocisti(tekst: str | None) -> str | None:
    """Pretvara vrednost u tekst, svaki niz razmaka i novih redova menja jednim razmakom i vraća None ako ništa ne ostane."""
    # str() mi treba jer iz JSON-LD-a ume da stigne i broj, a ne tekst
    if tekst is None:
        return None
    tekst = re.sub(r"\s+", " ", str(tekst)).strip()
    return tekst or None


def bez_dijakritika(tekst: str) -> str:
    """
    Vraća tekst malim slovima, bez kvačica i interpunkcije, spreman za poređenje.
    Slovo đ menjam ručno, jer ga NFKD ne razlaže na d i kvačicu. Interpunkciju
    uklanjam jer Gigatron piše 'TV, audio, video', a u podešavanjima je 'tv audio video'.
    """
    # NFKD rastavi slovo na osnovno slovo i kvačicu, a combining() mi kaže koji znak je kvačica
    razlozeno = unicodedata.normalize("NFKD", tekst.lower().replace("đ", "d"))
    bez_znakova = "".join(z for z in razlozeno if not unicodedata.combining(z))
    # interpunkciju menjam razmakom, pa višestruke razmake svodim na jedan
    bez_interpunkcije = re.sub(r"[^\w\s]", " ", bez_znakova)
    return re.sub(r"\s+", " ", bez_interpunkcije).strip()


def json_ld_blokovi(supa: BeautifulSoup) -> list[dict]:
    """
    Skuplja sve <script type="application/ld+json"> oznake i vraća listu blokova.
    Oznaku koja nije ispravan JSON preskače, a ako oznaka sadrži listu, dodaje sve njene elemente.
    """
    # stranica ima više JSON-LD oznaka (Product, BreadcrumbList...), pa ih sve skupljam u jednu listu
    blokovi = []
    for oznaka in supa.find_all("script", type="application/ld+json"):
        if not oznaka.string:
            continue
        try:
            sadrzaj = json.loads(oznaka.string)
        except Exception:
            continue
        blokovi.extend(sadrzaj if isinstance(sadrzaj, list) else [sadrzaj])
    return blokovi


def nadji_blok(blokovi: list[dict], tip: str) -> dict | None:
    """Vraća prvi blok čiji je @type jednak zadatom tipu, ili None ako takvog bloka nema."""
    # next sa podrazumevanom vrednošću None mi vraća prvi pogodak i ne prolazi ostatak liste
    return next((b for b in blokovi if b.get("@type") == tip), None)


# -------------------------------
# Kategorija
# -------------------------------
def putanja_kategorije(blokovi: list[dict]) -> list[str]:
    """
    Iz bloka BreadcrumbList vraća nazive kategorija, bez početne stranice i bez
    poslednje stavke, koja je naziv proizvoda.
    Primer: ['Bela tehnika', 'Frižideri', 'Kombinovani frižideri']
    """
    blok = nadji_blok(blokovi, "BreadcrumbList")
    if not blok:
        return []

    # naziv stavke je nekad u item.name, a nekad direktno u name, pa proveravam oba
    nazivi = []
    for stavka in blok.get("itemListElement", []):
        cilj = stavka.get("item")
        naziv = cilj.get("name") if isinstance(cilj, dict) else stavka.get("name")
        if naziv:
            nazivi.append(ocisti(naziv))

    # početnu stranicu ('Početna', 'Naslovna', 'Home') izbacujem ako je prva,
    # a poslednju stavku samo ako ih ima više od jedne
    if nazivi and bez_dijakritika(nazivi[0]) in {"pocetna", "naslovna", "home"}:
        nazivi = nazivi[1:]
    return nazivi[:-1] if len(nazivi) > 1 else nazivi


def pripada_beloj_tehnici(putanja: list[str]) -> bool:
    """
    Po putanji kategorije odlučuje da li proizvod ulazi u bazu. Svi nivoi se
    porede posle bez_dijakritika(), sa skupovima iz podesavanja.py.
    """
    # proizvod bez putanje kategorije ne mogu da svrstam, pa ga ne puštam u bazu
    if not putanja:
        return False

    prvi_nivo = bez_dijakritika(putanja[0])
    nizi_nivoi = [bez_dijakritika(nivo) for nivo in putanja[1:]]
    drugi_nivo = nizi_nivoi[0] if nizi_nivoi else ""

    # 1) oprema i dodaci ispadaju bez obzira na prvi nivo, na kom god nivou ispod njega stoje
    # („Usisivači/Oprema za usisivače“ je treći nivo)
    if any(nivo in pod.ISKLJUCENE_PODKATEGORIJE_GIGATRON for nivo in nizi_nivoi):
        return False

    # 2) iz 'TV, audio, video' zadržavam samo televizore
    if prvi_nivo == pod.KATEGORIJA_GIGATRON_TV:
        return drugi_nivo in pod.PODKATEGORIJE_GIGATRON_TV

    # 3) ostalo puštam ako je prvi nivo bela tehnika ili mali aparati
    return prvi_nivo in pod.KATEGORIJE_GIGATRON


# -------------------------------
# Karakteristike
# -------------------------------
def karakteristike_iz_tabele(supa: BeautifulSoup) -> list[tuple[str, str]]:
    """
    Čita tabelu specifikacija starijeg izgleda stranice, gde red ima tačno dve
    <td> ćelije: naziv i vrednost. Vraća listu parova (naziv, vrednost).
    """
    # red koji nema tačno dve ćelije nije red specifikacije, pa ga preskačem
    stavke, videno = [], set()
    for red in supa.select("tr"):
        celije = red.find_all("td", recursive=False)
        if len(celije) != 2:
            continue
        naziv = ocisti(celije[0].get_text(" "))
        vrednost = ocisti(celije[1].get_text(" "))
        if not naziv or not vrednost:
            continue
        # isti par, bez obzira na velika i mala slova, upisujem samo jednom
        kljuc = (naziv.lower(), vrednost.lower())
        if kljuc in videno:
            continue
        videno.add(kljuc)
        stavke.append((naziv, vrednost))
    return stavke


def vrednosti_iz_niza(sirovo: str) -> list[str]:
    """
    Sadržaj niza "values" pretvara u listu vrednosti. Niz je u HTML-u zapisan unutar
    JavaScript stringa, pa je navodnik oblika \\", navodnik za inče \\\\\\" (50\\\\\\" (127 cm)),
    a znak < oblika \\u003c. Zato tekst prvo čitam kao JSON string, a dobijeni tekst
    kao JSON listu. Ako čitanje ne uspe, vraćam ono što nađe VREDNOST_RE.
    """
    tekst = sirovo.strip()
    try:
        # niz koji počinje sa \" je unutar JavaScript stringa, pa jedan nivo \ skidam
        # tako što ga čitam kao JSON string; posle toga je to obična JSON lista
        if tekst.startswith('\\"'):
            tekst = json.loads(f'"{tekst}"')
        niz = json.loads(f"[{tekst}]")
    except ValueError:
        return VREDNOST_RE.findall(sirovo)

    # HTML oznake (<p>, <br />) menjam razmakom, a entitete (&nbsp;) vraćam u znakove
    return [unescape(OZNAKA_RE.sub(" ", str(vrednost))) for vrednost in niz]


def karakteristike_iz_payloada(html: str) -> list[tuple[str, str]]:
    """
    Vraća parove (naziv, vrednost) iz JSON zapisa u izvornom HTML-u. Noviji izgled
    stranice nema tabelu, nego se sadržaj sastavlja u pregledaču, pa bi bez ovoga
    veš-mašine i rerne sa Gigatrona imale samo jednu ili dve karakteristike.
    """
    stavke, videno = [], set()

    # regularni izraz puštam nad celim sirovim HTML-om, jer ovaj zapis nije u DOM stablu kao tabela
    for pogodak in PAYLOAD_KARAKTERISTIKA_RE.finditer(html):
        naziv = ocisti(pogodak.group("naziv"))
        # niz "values" može imati više vrednosti, pa ih spajam zarezom
        sirove_vrednosti = vrednosti_iz_niza(pogodak.group("vrednosti"))
        vrednost = ocisti(", ".join(v for v in sirove_vrednosti if v.strip()))

        if not naziv or not vrednost:
            continue
        # preskačem unutrašnja polja prodavnice i vrednosti koje su putanje do fajlova
        if UNUTRASNJA_POLJA_RE.search(naziv) or TEHNICKA_VREDNOST_RE.match(vrednost):
            continue

        # isti par ume da se pojavi više puta u HTML-u, pa onaj koji sam već videla ne dodajem opet
        kljuc = (naziv.lower(), vrednost.lower())
        if kljuc in videno:
            continue
        videno.add(kljuc)
        stavke.append((naziv, vrednost))

    return stavke


def energetska_klasa(supa: BeautifulSoup) -> tuple[str, str] | tuple[None, None]:
    """
    Prolazi kroz slike i po alt atributu nalepnice vraća par (klasa, skala),
    npr. ('F', 'Novo'). Ako skala ne piše, vraća 'nepoznato', a bez nalepnice (None, None).
    """
    # vraćam se čim nađem prvu sliku nalepnice; slika bez alt atributa daje prazan tekst
    for slika in supa.find_all("img"):
        pogodak = ENERGETSKA_RE.search(slika.get("alt") or "")
        if pogodak:
            return pogodak.group(1).upper(), ocisti(pogodak.group(2)) or "nepoznato"
    return None, None


# -------------------------------
# Glavna funkcija parsiranja
# -------------------------------
def parsiraj(html: str, samo_bela_tehnika: bool = True) -> dict | None:
    """
    Parsira jednu stranicu sa Gigatrona i vraća rečnik sa podacima o proizvodu.
    Vraća None ako nema bloka Product, ako se ne nađe adresa ili ako proizvod nije
    bela tehnika (tu proveru preskače kad je samo_bela_tehnika=False).
    """
    supa = BeautifulSoup(html, "lxml")
    blokovi = json_ld_blokovi(supa)

    # bez bloka Product ovo nije stranica proizvoda, pa dalje ni ne gledam
    proizvod = nadji_blok(blokovi, "Product")
    if not proizvod:
        return None

    # ovde odbacujem sve što nije bela tehnika, jer na Gigatronu to nisam mogla da uradim po adresi
    putanja = putanja_kategorije(blokovi)
    if samo_bela_tehnika and not pripada_beloj_tehnici(putanja):
        return None

    # offers je nekad rečnik, a nekad lista ponuda, pa tada uzimam prvu
    ponuda = proizvod.get("offers") or {}
    if isinstance(ponuda, list):
        ponuda = ponuda[0] if ponuda else {}

    # brend je nekad objekat sa poljem name, a nekad običan tekst
    marka = proizvod.get("brand") or {}
    brend = marka.get("name") if isinstance(marka, dict) else marka

    # dostupnost je puna adresa ('https://schema.org/InStock'), pa uzimam deo posle poslednje kose crte
    oznaka_dostupnosti = str(ponuda.get("availability") or "")
    kljuc_dostupnosti = oznaka_dostupnosti.rsplit("/", 1)[-1].lower()
    na_stanju = DOSTUPNOST.get(kljuc_dostupnosti)

    # ocene kupaca su u aggregateRating; kad ga nema, prazan rečnik mi daje None ispod
    ocene = proizvod.get("aggregateRating") or {}

    # adresu uzimam iz ponude, a ako je tamo nema, iz kanonske oznake stranice
    url = ocisti(ponuda.get("url"))
    if not url:
        kanonska = supa.find("link", rel="canonical")
        url = kanonska.get("href") if kanonska else None
    if not url:
        return None

    # karakteristike: prvo tabela (stariji izgled), pa JSON zapis (noviji izgled),
    # a par koji sam već pročitala iz tabele ne dodajem ponovo
    karakteristike = karakteristike_iz_tabele(supa)
    videno = {(n.lower(), v.lower()) for n, v in karakteristike}
    for naziv_atributa, vrednost in karakteristike_iz_payloada(html):
        if (naziv_atributa.lower(), vrednost.lower()) not in videno:
            karakteristike.append((naziv_atributa, vrednost))
    # energetsku klasu dodajem kao običnu karakteristiku, pod istim nazivom kao kod winwin.rs,
    # da je čišćenje u Zadatku 2 nađe; ne dodajem je ako već postoji "Energetska klasa..."
    klasa, skala = energetska_klasa(supa)
    if klasa and not any(k.lower().startswith("energetska klasa") for k, _ in karakteristike):
        karakteristike.append(("Energetska klasa", f"{klasa} ({skala})"))

    # sku tražim i u productID ako ga nema, a cenu, ocenu i broj ocena pretvaram u broj samo kad postoje;
    # ključevi su isti kao u parser_magento.py, da upis radi isto za obe prodavnice
    return {
        "url":             url,
        "sku":             ocisti(proizvod.get("sku")) or ocisti(proizvod.get("productID")),
        "naziv":           ocisti(proizvod.get("name")),
        "brend":           ocisti(brend),
        "kategorija_puna": "/".join(putanja) if putanja else None,
        "kategorija":      putanja[-1] if putanja else None,
        "cena":            float(ponuda["price"]) if ponuda.get("price") not in (None, "") else None,
        "valuta":          ocisti(ponuda.get("priceCurrency")) or "RSD",
        "dostupnost":      oznaka_dostupnosti.rsplit("/", 1)[-1] or None,
        "na_stanju":       na_stanju,
        "ocena":           float(ocene["ratingValue"]) if ocene.get("ratingValue") else None,
        "broj_ocena":      int(ocene["reviewCount"]) if ocene.get("reviewCount") else None,
        "opis":            ocisti(proizvod.get("description")),
        "karakteristike":  karakteristike,
    }


# -------------------------------
# Samostalna proba nad jednim fajlom
# -------------------------------
def main() -> None:
    """Parsira jedan snimljeni fajl zadat sa --fajl i ispisuje sva polja i karakteristike."""
    # sa --sve_kategorije isključujem filter bele tehnike, da vidim i ostale proizvode
    parser = argparse.ArgumentParser(description="Proba Gigatron parsera nad jednom snimljenom stranicom.")
    parser.add_argument("--fajl", required=True, help="putanja do .html.gz fajla")
    parser.add_argument("--sve_kategorije", action="store_true",
                        help="ne filtrirati na belu tehniku (za pregled)")
    argumenti = parser.parse_args()

    podaci = parsiraj(procitaj_html(Path(argumenti.fajl)),
                      samo_bela_tehnika=not argumenti.sve_kategorije)
    if not podaci:
        print("[INFO] Stranica nije proizvod bele tehnike ili nije prepoznata.")
        return

    # ostala polja skraćujem na 100 znakova, jer opis ume da bude dugačak
    for kljuc, vrednost in podaci.items():
        if kljuc == "karakteristike":
            print(f"[INFO] karakteristike ({len(vrednost)}):")
            for naziv, vred in vrednost:
                print(f"         {naziv:35} = {vred[:60]}")
        else:
            print(f"[INFO] {kljuc:16} = {str(vrednost)[:100]}")


if __name__ == "__main__":
    main()
