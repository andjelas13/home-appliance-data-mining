#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
podesavanja.py — Podešavanja veb indeksera (Zadatak 1).

Opis:
Ovde su adrese sitemap fajlova, kategorije koje ulaze u bazu, tempo zahteva i
zaglavlja. Indekser, parser_gigatron.py i upis_u_bazu.py čitaju podešavanja
odavde, pa se za novu prodavnicu dodaje samo unos u rečnik PRODAVNICE.

Izvori podataka:
- winwin.rs   — Magento; nije sa spiska iz projektnog zadatka. Kategorija se
                čita iz putanje adrese, a stranicu pravi server, pa su svi
                podaci već u preuzetom HTML-u.
- gigatron.rs — Next.js; podaci su u semantičkim anotacijama (JSON-LD,
                schema.org), pa se koristi drugačija tehnika parsiranja.

Opterećenje servera:
Između zahteva je uvek pauza (PAUZA_SEKUNDI uz slučajno odstupanje), poštuje
se robots.txt i radi najviše BROJ_RADNIKA niti, da tempo ne liči na napad.
"""

# -------------------------------
# Tempo i mrežna podešavanja
# -------------------------------
# sve brojeve za tempo držim na jednom mestu, da ih menjam ovde, a ne po kodu indeksera
PAUZA_SEKUNDI       = 0.6    # osnovna pauza koju pravim između dva zahteva istog radnika
PAUZA_ODSTUPANJE    = 0.4    # pauzu pomeram nasumično za ovoliko (±), da ritam ne bude pravilan
BROJ_RADNIKA        = 5      # ovoliko niti mi paralelno preuzima stranice
VREME_CEKANJA       = 25     # najduže što čekam odgovor servera, u sekundama
BROJ_POKUSAJA       = 3      # ukupno pokušaja koje dajem jednoj adresi
PAUZA_POSLE_GRESKE  = 5.0    # pauza posle neuspeha, koju množim rednim brojem pokušaja

# stavila sam zaglavlja običnog pregledača (Chrome), jer prodavnice odbijaju zahtev
# sa Python zaglavljem; ista zaglavlja šaljem i za robots.txt, čija pravila poštujem
# (indekser.ucitaj_robots)
ZAGLAVLJA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# -------------------------------
# Kategorije kod winwin.rs
# -------------------------------
# ključ mi je kategorija prvog nivoa iz adrese, a True znači da je puštam u bazu;
# uzimam belu tehniku, klime, male kućne aparate i televizore, a IT opremu,
# telefone i ostalo preskačem, jer zadatak traži belu tehniku
KATEGORIJE_MAGENTO = {
    "bela-tehnika":                     True,
    "klime-grejanje-i-kvalitet-vazduha": True,
    "mali-kucni-aparati":               True,
    "tv-foto-audio-i-video":            True,   # od ove kategorije zadržavam samo televizore
    "it-gaming":                        False,
    "telefoni-smart-satovi-i-tableti":  False,
    "auto-oprema":                      False,
    "lepota-i-zdravlje":                False,
    "kuca-basta-i-alati":               False,
    "lifestyle":                        False,
    "bebe-i-deca":                      False,
}

# drugi nivo koji zadržavam unutar 'tv-foto-audio-i-video';
# slušalice, zvučnici i foto-aparati nisu bela tehnika
PODKATEGORIJE_TV = {"televizori"}

# podkategorije koje izbacujem iako su pod dozvoljenom kategorijom (na drugom ili trećem
# nivou adrese, npr. /mali-kucni-aparati/oprema-za-ciscenje-kuhinjskih-aparata/...):
# oprema, delovi i potrošni materijal nisu uređaji, nemaju energetsku klasu, zapreminu
# ni snagu, pa bi mi samo smetali u modelima iz zadataka 4, 5 i 6
ISKLJUCENE_PODKATEGORIJE = {
    "dodatna-oprema-za-usisivace",
    "dodatna-oprema-za-sporete",
    "dodatna-oprema-za-rerne-i-ploce",
    "dodatna-oprema-za-frizidere-i-zamrzivace",
    "filteri-creva-i-ostala-oprema-za-aspiratore",
    "filteri-i-oprema-za-preciscavanje-vazduha",
    "filteri-za-bokale-za-vodu",
    "oprema-za-ves-masine",
    "oprema-za-sudomasine",
    "oprema-za-ciscenje-kuhinjskih-aparata",
    "kafa-cajevi-i-kapsule-za-kafu",
}

# spisak adresa mešam pre preuzimanja, da i prekinuto preuzimanje ima stranice iz
# svih kategorija, a ne samo s početka abecede; seme sam fiksirala na 2026, pa je
# redosled uvek isti i mogu da ga proverim
SEME_MESANJA = 2026

# -------------------------------
# Kategorije kod Gigatrona
# -------------------------------
# adresa proizvoda na Gigatronu nema kategoriju (sve je /proizvod/<naziv>), pa je čitam
# iz JSON-LD BreadcrumbList oznake; ovde sam upisala prvi nivo malim slovima, bez
# kvačica i interpunkcije, jer tako poredim (parser_gigatron.bez_dijakritika)
KATEGORIJE_GIGATRON = {
    "bela tehnika",
    "mali kucni aparati",
    "mali kuhinjski aparati",
}

# iz kategorije 'TV, audio, video' puštam samo drugi nivo 'Televizori'
KATEGORIJA_GIGATRON_TV      = "tv audio video"
PODKATEGORIJE_GIGATRON_TV   = {"televizori"}

# podkategorije (drugi ili treći nivo) koje izbacujem u svakoj kategoriji, jer su to
# oprema, dodaci i potrošni materijal, a ne uređaji
ISKLJUCENE_PODKATEGORIJE_GIGATRON = {
    "oprema za belu tehniku",
    "nastavci i dodaci",
    "dodatna oprema za tv",
    "dodatna oprema za projektore",
    "ostala oprema",
    "kablovi i adapteri",
    "oprema za usisivace",
    "oprema za peglanje",
    "oprema za espresso aparate",
    "dodaci za pripremu kafe",
    "kafe",
    "zamenski filteri i dodatna oprema",
    "flasice",
    "oprema za klima uredaje",
    "dodatna oprema za sporete",
    "dodatna oprema za grejna tela",
}

# -------------------------------
# Izvori podataka
# -------------------------------
# ključ mi je šifra prodavnice iz tabele primarna.prodavnice; preko 'parser' biram
# modul za parsiranje, a Gigatronu sam umesto spiska sitemap fajlova dala sitemap indeks
PRODAVNICE = {
    "winwin": {
        "naziv":        "Win Win",
        "osnovni_url":  "https://www.winwin.rs",
        "parser":       "magento",
        "sitemap":      [
            "https://www.winwin.rs/products_1.xml",
            "https://www.winwin.rs/products_2.xml",
            "https://www.winwin.rs/products_3.xml",
        ],
    },
    "gigatron": {
        "naziv":        "Gigatron",
        "osnovni_url":  "https://gigatron.rs",
        "parser":       "gigatron",
        "sitemap_indeks": "https://gigatron.rs/sitemap/proizvodi.xml",
    },
}

# -------------------------------
# Putanje
# -------------------------------
FOLDER_HTML = "preuzeto"     # ovde čuvam snimljene stranice, da parsiranje ponovim bez novog preuzimanja
FOLDER_LOG  = "log"          # ovde mi idu spiskovi adresa i zapisi o radu indeksera
