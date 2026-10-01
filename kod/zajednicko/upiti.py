#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
upiti.py — Zajednički SQL upiti za upis proizvoda u primarnu bazu.

Opis:
Modul sadrži UPIT_PROIZVOD, kojim upis_u_bazu.py upisuje jedan proizvod i dobija
njegov id. Proizvod se prepoznaje po paru (prodavnica_id, url), pa ponovno
pokretanje ažurira postojeći zapis umesto da pravi duplikat. UPIT_DATUM_PREUZIMANJA
posle upisa prepisuje vreme preuzimanja iz dnevnika indeksiranja.
"""

# -------------------------------
# Upis proizvoda
# -------------------------------
# Upit sam napisala sa imenovanim parametrima %(ime)s, pa mu prosleđujem rečnik proizvoda.
# ON CONFLICT mi ažurira postojeći red; za šifru, dostupnost, na_stanju, ocenu, broj ocena i opis
# COALESCE zadržava staru vrednost kad parser nije našao novu. datum_preuzimanja ovde ne diram,
# jer ga posle upisa prepisuje UPIT_DATUM_PREUZIMANJA.
# RETURNING id mi vraća id i novog i ažuriranog proizvoda.
UPIT_PROIZVOD = """
    INSERT INTO primarna.proizvodi
        (prodavnica_id, url, sku, naziv, brend, kategorija_puna, kategorija,
         cena, valuta, dostupnost, na_stanju, ocena, broj_ocena, opis)
    VALUES (%(prodavnica_id)s, %(url)s, %(sku)s, %(naziv)s, %(brend)s,
            %(kategorija_puna)s, %(kategorija)s, %(cena)s, %(valuta)s,
            %(dostupnost)s, %(na_stanju)s, %(ocena)s, %(broj_ocena)s, %(opis)s)
    ON CONFLICT (prodavnica_id, url) DO UPDATE SET
        sku               = COALESCE(EXCLUDED.sku, primarna.proizvodi.sku),
        naziv             = EXCLUDED.naziv,
        brend             = EXCLUDED.brend,
        kategorija_puna   = EXCLUDED.kategorija_puna,
        kategorija        = EXCLUDED.kategorija,
        cena              = EXCLUDED.cena,
        valuta            = EXCLUDED.valuta,
        dostupnost        = COALESCE(EXCLUDED.dostupnost, primarna.proizvodi.dostupnost),
        na_stanju         = COALESCE(EXCLUDED.na_stanju, primarna.proizvodi.na_stanju),
        ocena             = COALESCE(EXCLUDED.ocena, primarna.proizvodi.ocena),
        broj_ocena        = COALESCE(EXCLUDED.broj_ocena, primarna.proizvodi.broj_ocena),
        opis              = COALESCE(EXCLUDED.opis, primarna.proizvodi.opis)
    RETURNING id
"""

# -------------------------------
# Vreme preuzimanja
# -------------------------------
# Stranicu je indekser preuzeo satima pre parsiranja, pa vreme preuzimanja uzimam iz
# dnevnika indeksiranja: adresa proizvoda je ista kao adresa uspešne posete u dnevniku.
# Dnevnik se upisuje u paketima, pa je upisano vreme do dvadesetak minuta posle samog
# preuzimanja stranice; početak i kraj perioda se time ne menjaju.
# Parametar %s je id prodavnice, da prepisujem samo proizvode prodavnice koju sam upisala.
UPIT_DATUM_PREUZIMANJA = """
    UPDATE primarna.proizvodi p
    SET    datum_preuzimanja = d.vreme
    FROM   primarna.dnevnik_indeksiranja d
    WHERE  d.prodavnica_id = p.prodavnica_id
      AND  d.url = p.url
      AND  d.uspesno
      AND  p.prodavnica_id = %s
"""
