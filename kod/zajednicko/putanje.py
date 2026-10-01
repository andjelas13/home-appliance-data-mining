#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
putanje.py — Zajedničke putanje do foldera sa rezultatima.

Opis:
Modul u korenu projekta traži folder sa rezultatima, prvo pod nazivom
„izveštaj“, pa „izvestaj“, i uzima onaj koji postoji. Ako nema nijednog,
koristi „izveštaj“. Sve skripte uzimaju putanje odavde, pa se naziv foldera ne
ponavlja u svakoj od njih.

Primer upotrebe:
    from zajednicko.putanje import FOLDER_IZVESTAJA, FOLDER_MODELA, FOLDER_GRAFIKONA
"""

from __future__ import annotations

from pathlib import Path

# koren projekta mi je dva nivoa iznad kod/zajednicko; tu su kod, baza i izveštaj
KOREN = Path(__file__).resolve().parents[2]

# prvo tražim naziv iz projektnog zadatka, pa isti naziv bez kvačice
MOGUCI_NAZIVI = ("izveštaj", "izvestaj")


def nadji_folder_izvestaja() -> Path:
    """
    Vraća prvi folder iz MOGUCI_NAZIVI koji postoji u korenu projekta; ako ne
    postoji nijedan, vraća putanju sa nazivom iz zadatka (folder ne pravi).
    """
    # vraćam prvi naziv koji postoji kao folder, redom kojim sam ih navela
    for naziv in MOGUCI_NAZIVI:
        kandidat = KOREN / naziv
        if kandidat.is_dir():
            return kandidat
    # ako je alat za raspakivanje pokvario slovo š u nazivu, uzimam prvi folder koji počinje sa „izve“
    for kandidat in sorted(KOREN.glob("izve*")):
        if kandidat.is_dir():
            return kandidat
    # ako ga nema, vraćam putanju sa kvačicom, a folder pravi skripta koja upisuje
    return KOREN / MOGUCI_NAZIVI[0]


# ovde računam folder izveštaja jednom, a iz njega podfoldere za snimljene modele i grafikone
FOLDER_IZVESTAJA = nadji_folder_izvestaja()
FOLDER_MODELA = FOLDER_IZVESTAJA / "modeli"
FOLDER_GRAFIKONA = FOLDER_IZVESTAJA / "grafikoni"


# kad pokrenem ovaj fajl direktno, samo ispišem koje sam putanje našla
if __name__ == "__main__":
    print(f"[INFO] Koren projekta:    {KOREN}")
    print(f"[INFO] Folder izveštaja:  {FOLDER_IZVESTAJA}  (postoji: {FOLDER_IZVESTAJA.is_dir()})")
