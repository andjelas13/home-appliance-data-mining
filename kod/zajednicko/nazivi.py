#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nazivi.py — Čitljivi nazivi kategorija i karakteristika za prikaz.

Opis:
U bazi su kategorije zapisane kao oznake bez kvačica, sa donjom crtom
('ves_masina', 'sudo_masina'), jer se koriste kao ključevi u kodu, u nazivima
kolona i u imenima fajlova. Za grafikone, izveštaj i aplikaciju treba
pravilno napisan srpski naziv, pa sam prevod stavila na jedno mesto i svi ga
uzimaju odavde.

Sadrži:
    KATEGORIJE, kategorija()           — čitljiv naziv kategorije uređaja
    KARAKTERISTIKE, obelezje_modela()  — čitljiv naziv karakteristike i
                                         kolone iz matrice obeležja modela
"""

from __future__ import annotations

# -------------------------------
# Kategorije uređaja
# -------------------------------
# ovde sam povezala oznaku kategorije iz prečišćene baze sa nazivom za prikaz
KATEGORIJE = {
    "televizor":            "Televizori",
    "frizider":             "Frižideri",
    "zamrzivac":            "Zamrzivači",
    "ves_masina":           "Veš-mašine",
    "ves_masina_susilica":  "Veš-mašine sa sušenjem",
    "susilica":             "Sušilice veša",
    "sudo_masina":          "Mašine za sudove",
    "sporet":               "Šporeti",
    "rerna":                "Rerne",
    "ugradna_ploca":        "Ugradne ploče",
    "aspirator":            "Aspiratori",
    "mikrotalasna":         "Mikrotalasne rerne",
    "bojler":               "Bojleri",
    "klima":                "Klima-uređaji",
    "grejalica":            "Grejalice i radijatori",
    "ventilator":           "Ventilatori",
    "preciscivac_vazduha":  "Prečišćivači vazduha",
    "ovlazivac_vazduha":    "Ovlaživači i odvlaživači",
    "usisivac":             "Usisivači",
    "parocistac":           "Paročistači",
    "pegla":                "Pegle i parne stanice",
    "aparat_za_kafu":       "Aparati za kafu",
    "friteza":              "Friteze i airfryeri",
    "blender":              "Blenderi i sokovnici",
    "mikser":               "Mikseri i multipraktici",
    "toster":               "Tosteri",
    "mini_pekara":          "Mini pekare",
    "masina_za_meso":       "Mašine za meso",
    "kuvalo_za_vodu":       "Kuvala za vodu",
    "kuhinjska_vaga":       "Kuhinjske vage",
    "reso":                 "Rešoi",
    "masina_za_sivenje":    "Mašine za šivenje",
    "rashladna_vitrina":    "Rashladne i vinske vitrine",
    "toplotna_pumpa":       "Toplotne pumpe",
    "rostilj":              "Roštilji i grilovi",
    "ledomat":              "Ledomati",
    "ugradni_set":          "Ugradni setovi",
    "ostali_kuhinjski_aparat": "Ostali kuhinjski aparati",
    "ostali_kucni_aparat":  "Ostali kućni aparati",
}


def kategorija(oznaka: str | None) -> str:
    """
    Vraća naziv kategorije iz rečnika KATEGORIJE. Oznaku koje nema u rečniku
    piše sa razmacima umesto donje crte i velikim prvim slovom, a za praznu vraća crtu.
    """
    # za praznu oznaku vraćam crtu, da u tabeli ne piše None
    if not oznaka:
        return "—"
    # ako neku oznaku nisam upisala u rečnik, pravim naziv od same oznake
    return KATEGORIJE.get(oznaka, oznaka.replace("_", " ").capitalize())


# -------------------------------
# Karakteristike (nazivi kolona u bazi i u modelu)
# -------------------------------
# za svaku kolonu sam napisala kratak opis sa jedinicom mere, za ose i legende grafikona
KARAKTERISTIKE = {
    "cena_min":                 "cena",
    "dijagonala_inch":          "dijagonala (inč)",
    "zapremina_l":              "zapremina (l)",
    "zapremina_frizider_l":     "zapremina frižidera (l)",
    "zapremina_zamrzivac_l":    "zapremina zamrzivača (l)",
    "kapacitet_pranja_kg":      "kapacitet pranja (kg)",
    "kapacitet_kompleta":       "kapacitet (kompleta)",
    "brzina_centrifuge":        "brzina centrifuge",
    "snaga_w":                  "snaga (W)",
    "kapacitet_hladjenja_kw":   "rashladni učinak (kW)",
    "visina_cm":                "visina (cm)",
    "sirina_cm":                "širina (cm)",
    "dubina_cm":                "dubina (cm)",
    "tezina_kg":                "težina (kg)",
    "nivo_buke_db":             "nivo buke (dB)",
    "broj_programa":            "broj programa",
    "gabarit_cm3":              "gabarit (cm³)",
    "energetska_rang":          "energetski rang",
}


def obelezje_modela(naziv: str) -> str:
    """
    Pretvara naziv kolone iz matrice obeležja u tekst za grafikon. Prepoznaje tri
    oblika iz pripreme podataka: 'brend=Bosch' (one-hot), 'snaga_w_nedostaje'
    (pokazatelj prazne vrednosti) i 'snaga_w×frizider' (član interakcije).
    Ostale nazive traži u rečniku KARAKTERISTIKE.
    """
    # Član interakcije delim na znaku ×: levi deo prevodim ovom istom funkcijom, desni mi je kategorija.
    if "×" in naziv:
        karakteristika, oznaka_kategorije = naziv.split("×", 1)
        return f"{obelezje_modela(karakteristika)} × {kategorija(oznaka_kategorije).lower()}"
    # one-hot kolonu delim na znaku =; kad je u pitanju kategorija, prevodim i vrednost
    if "=" in naziv:
        vrsta, vrednost = naziv.split("=", 1)
        if vrsta == "kategorija":
            return f"kategorija: {kategorija(vrednost).lower()}"
        return f"{vrsta.replace('_', ' ')}: {vrednost}"
    # pokazatelj da podatak nedostaje: odsecam nastavak _nedostaje i prevodim ostatak
    if naziv.endswith("_nedostaje"):
        return f"bez podatka: {obelezje_modela(naziv[:-len('_nedostaje')])}"
    # sve ostalo su obične kolone, pa ih tražim u rečniku KARAKTERISTIKE
    return KARAKTERISTIKE.get(naziv, naziv.replace("_", " "))
