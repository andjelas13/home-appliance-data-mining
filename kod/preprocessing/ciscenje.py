#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ciscenje.py — Preprocesiranje primarne baze i formiranje prečišćene baze
              (Zadatak 2).

Opis:
Skripta čita sirove proizvode i karakteristike iz šeme primarna i puni šemu
preciscena. Kategorije svodi na kontrolisani rečnik (kod zbirne kategorije
vrstu uređaja čita iz naziva) i odbacuje pribor koji prepozna po nazivu
(korak 1), iz teksta karakteristika vadi brojeve u osnovnoj jedinici mere,
bez šablonskih vrednosti iz tabele filtera (korak 2), i razdvaja
energetsku klasu od skale, koju određuje po oznaci u tekstu ili po vrsti
uređaja (korak 3). Oznaku modela uzima iz karakteristike 'Model' ili iz naziva
i od brenda i modela pravi ključ spajanja, a outlet oglas dobija poseban ključ
(korak 4). Grupu u kojoj su dva oglasa iste prodavnice sa različitim nazivom
deli po nazivu (korak 4a), a kad Gigatron nema pravu oznaku modela, isti uređaj
iz dve prodavnice prepoznaje i po nazivu (korak 4b).
Isti uređaj iz više prodavnica spaja u jedan red sa najnižom, najvišom i
prosečnom cenom (korak 5) i računa cenu po inču, litru, kilogramu i kW
(korak 6). Broj odbačenih, spojenih i upisanih zapisa beleži u tabelu
dnevnik_ciscenja, a prečišćenu bazu pri svakom pokretanju puni ispočetka.

Ulazi:
    šema primarna (tabele proizvodi, prodavnice i karakteristike)

Izlazi:
    šema preciscena (tabele proizvodi, poreklo i dnevnik_ciscenja)

Primer poziva:
    python ciscenje.py
    python ciscenje.py --min_karakteristika 4
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# dodajem folder kod (zbog zajednicko.baza) i ovaj folder (zbog pravila.py),
# da bi importi radili i kad skriptu pokrenem iz drugog foldera
sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

from zajednicko.baza import veza
import pravila

# -------------------------------
# Jedinice mere
#   uz svaku jedinicu sam stavila obrasce (broj + oznaka) i množilac za svođenje
#   na osnovnu jedinicu, npr. mm u cm množim sa 0.1, a kW u W sa 1000
# -------------------------------
# Obrasce jedne jedinice probam redom i prvi koji se poklopi daje vrednost.
# Za 'broj' uzimam samo cifre sa početka teksta, npr. '15 programa' daje 15.
JEDINICE = {
    # dijagonala se piše sa znakom za inč ('50" (127 cm)') ili rečju ('50 inča');
    # kad oznake inča nema, dijagonalu računam iz centimetara (139.7 cm / 2.54 = 55 inča)
    "inch":     [(r'(\d+(?:[.,]\d+)?)\s*(?:"|\'\'|”|inc|in\b)', 1.0),
                 (r'(\d+(?:[.,]\d+)?)\s*cm\b', 1 / 2.54)],
    "l":        [(r'(\d+(?:[.,]\d+)?)\s*(?:l\b|lit)', 1.0),
                 (r'(\d+(?:[.,]\d+)?)\s*ml\b', 0.001)],
    "kg":       [(r'(\d+(?:[.,]\d+)?)\s*kg\b', 1.0),
                 (r'(\d+(?:[.,]\d+)?)\s*g\b', 0.001)],
    "w":        [(r'(\d+(?:[.,]\d+)?)\s*kw\b', 1000.0),
                 (r'(\d+(?:[.,]\d+)?)\s*w\b', 1.0)],
    # rashladni učinak ume da piše i u vatima ('3520 W'), pa W delim sa 1000
    "kw":       [(r'(\d+(?:[.,]\d+)?)\s*kw\b', 1.0),
                 (r'(\d+(?:[.,]\d+)?)\s*w\b', 0.001)],
    "btu":      [(r'(\d+(?:[.,]\d+)?)\s*btu', 1.0)],
    "cm":       [(r'(\d+(?:[.,]\d+)?)\s*cm\b', 1.0),
                 (r'(\d+(?:[.,]\d+)?)\s*mm\b', 0.1),
                 (r'(\d+(?:[.,]\d+)?)\s*m\b', 100.0)],
    # Winwin kod frižidera ume da napiše nivo buke samo brojem ('37'); karakteristika se
    # zove 'nivo buke', pa gol broj uzimam kao dB, a besmislice odbacuje opseg 10–100 dB.
    # Zagrada ispred dB je dozvoljena, jer kod mašina za sudove piše '46 (dB(A)'
    "db":       [(r'(\d+(?:[.,]\d+)?)\s*\(?db', 1.0),
                 (r'^(\d+(?:[.,]\d+)?)$', 1.0)],
    "kwh":      [(r'(\d+(?:[.,]\d+)?)\s*kwh', 1.0)],
    "obr/min":  [(r'(\d+(?:[.,]\d+)?)\s*(?:obr|rpm|o/min)', 1.0)],
    "kompleta": [(r'(\d+)\s*komplet', 1.0)],
    "broj":     [(r'^(\d+)', 1.0)],
}

# rezolucija: dva broja od 3 do 5 cifara razdvojena sa x ili ×, npr. '1920 x 1080'
REZOLUCIJA_RE = re.compile(r'(\d{3,5})\s*[x×]\s*(\d{3,5})')
# hvata tri broja razdvojena sa x, sa jedinicom iza svakog broja ili samo na kraju:
# '17,2 cm x 7 cm x 16 cm', '60 x 85 x 60 cm' i '343 mm x 380 mm x 440 mm'
DIMENZIJE_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*(mm|cm)?\s*[x×]\s*'
                          r'(\d+(?:[.,]\d+)?)\s*(mm|cm)?\s*[x×]\s*'
                          r'(\d+(?:[.,]\d+)?)\s*(mm|cm)\b')
# svaki broj iza kog piše cm, za zapis dimenzija bez znaka x
CM_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*cm')
# Gigatron ponekad piše razmak ispred decimalne tačke ('54 .8 cm'), pa ga brišem
RAZMAK_U_BROJU_RE = re.compile(r"(\d)\s+([.,]\d)")
# ovim svodim više razmaka, tabova i novih redova na jedan razmak
RAZMAK_RE = re.compile(r"\s+")


# -------------------------------
# Pomoćne funkcije
# -------------------------------
def normalizuj(tekst: str | None) -> str:
    """
    Funkcija svodi tekst na mala slova, bez kvačica i sa jednim razmakom
    između reči. Slovo 'đ' menjam u 'dj' posebno, jer ga NFKD ne razlaže,
    a nazivi u pravila.SINONIMI su pisani sa 'dj' ('kapacitet hladjenja').
    """
    # za None ili prazan tekst vraćam prazan string, da pozivi posle ne pucaju
    if not tekst:
        return ""
    tekst = str(tekst).lower().replace("đ", "dj")
    # NFKD mi rastavlja 'č' na 'c' i kvačicu, pa kvačice (combining znakove) samo izbacim
    razlozeno = unicodedata.normalize("NFKD", tekst)
    bez_kvacica = "".join(z for z in razlozeno if not unicodedata.combining(z))
    return RAZMAK_RE.sub(" ", bez_kvacica).strip()


def u_broj(tekst: str) -> float | None:
    """
    Pretvara tekst broja u float po srpskom zapisu: zarez je decimalni znak
    ('121,5' → 121.5), a tačka ispred tačno tri cifre je hiljadica
    ('1.200' → 1200), osim kad broj počinje nulom ('0.701' → 0.701).
    Ako tekst nije broj, vraća None.
    """
    tekst = tekst.strip()
    # kad ima zarez, tačke su mi hiljadice ('1.299,99'), pa njih brišem, a zarez postaje tačka
    if "," in tekst:
        tekst = tekst.replace(".", "").replace(",", ".")
    # bez zareza tačke brišem samo kad iza svake stoje tačno tri cifre, a broj ne počinje nulom
    # ('1.200' je 1200), pa '2.5' ostaje 2.5, a '0.701' ostaje 0.701
    elif re.fullmatch(r"[1-9]\d{0,2}(\.\d{3})+", tekst):
        tekst = tekst.replace(".", "")
    # ako ni posle ovoga nije broj, float baca ValueError, a ja tada vraćam None
    try:
        return float(tekst)
    except ValueError:
        return None


def izvuci_vrednost(sirovo: str, jedinica: str) -> float | None:
    """
    Iz teksta karakteristike vadi broj u traženoj jedinici i svodi ga na
    osnovnu jedinicu; ako jedinice nema u tekstu, vraća None (osim za 'broj').
    Tražim jedinicu zato što se 'Kapacitet' kod klime piše '12000 BTU', a kod
    friteze '10 l', pa litri ne smeju da uđu u kolonu za BTU.
    """
    tekst = RAZMAK_U_BROJU_RE.sub(r"\1\2", normalizuj(sirovo))
    # probam obrasce te jedinice redom; prvi koji nađe broj daje vrednost pomnoženu množiocem
    for obrazac, mnozilac in JEDINICE.get(jedinica, []):
        pogodak = re.search(obrazac, tekst)
        if pogodak:
            broj = u_broj(pogodak.group(1))
            if broj is not None:
                return broj * mnozilac
    return None


def u_opsegu(polje: str, vrednost: float | None, vrsta: tuple = ()) -> float | None:
    """
    Proverava vrednost prema granicama i vraća je ako je u opsegu, a None ako
    nije. Vrsta je par (kategorija, grupa): prvo gledam granicu kategorije, pa
    grupe iz pravila.OPSEZI_PO_VRSTI, a tek onda opštu iz pravila.OPSEZI.
    Polje koje nema granice prolazi bez provere.
    """
    if vrednost is None:
        return None
    # granice čitam iz pravila.py; next vraća prvu granicu koju nađe za kategoriju ili grupu
    granice = next((pravila.OPSEZI_PO_VRSTI[k][polje] for k in vrsta
                    if polje in pravila.OPSEZI_PO_VRSTI.get(k, {})), pravila.OPSEZI.get(polje))
    if not granice:
        return vrednost
    # obe granice su mi uključene, pa i vrednost tačno na granici prolazi
    donja, gornja = granice
    return vrednost if donja <= vrednost <= gornja else None


# -------------------------------
# Korak 1: kategorija
# -------------------------------
def odredi_kategoriju(izvorna: str | None, puna: str | None,
                      naziv: str | None = None) -> tuple[str, str] | None:
    """
    Svodi naziv kategorije sa sajta na kontrolisani rečnik. Gleda poslednji
    nivo kategorije, a punu putanju samo kad njega nema. Kad je kategorija
    zbirna ('Kućni aparati'), vrstu uređaja traži u nazivu proizvoda. Vraća par
    (kategorija, grupa) ili None ako to nije uređaj koji ulazi u bazu.
    """
    # kad je poslednji nivo prazan, normalizuj vraća '', pa 'or' uzima punu putanju
    tekst = normalizuj(izvorna) or normalizuj(puna)
    if not tekst:
        return None

    # 1) prvo izbacujem pribor, delove i potrošni materijal, da npr. 'kese za usisivač'
    #    ne bi posle upale u kategoriju usisivac
    for obrazac in pravila.KATEGORIJE_ZA_IZBACIVANJE:
        if re.search(obrazac, tekst):
            return None

    # 2) pravila proveravam redom i prvo poklapanje mi određuje kategoriju
    for obrazac, kategorija, grupa in pravila.KATEGORIJE:
        if re.search(obrazac, tekst):
            # 3) zbirna kategorija ne kaže vrstu, pa ista pravila probam nad nazivom proizvoda
            #    i uzimam prvo poklapanje iz dozvoljenih grupa; ako ga nema, ostaje zbirna
            if kategorija in pravila.ZBIRNE_KATEGORIJE and naziv:
                naziv = normalizuj(naziv)
                po_nazivu = [(k, g) for o, k, g in pravila.KATEGORIJE
                             if re.search(o, naziv) and g in pravila.ZBIRNE_KATEGORIJE[kategorija]]
                return po_nazivu[0] if po_nazivu else (kategorija, grupa)
            return kategorija, grupa
    return None


# -------------------------------
# Korak 2 i 3: karakteristike i energetska klasa
# -------------------------------
def tipiziraj_karakteristike(mapa: dict[str, list[str]], vrsta: tuple = ()) -> dict:
    """
    Prima rečnik {naziv karakteristike: lista vrednosti} i par (kategorija, grupa),
    prolazi kroz sinonime, rezoluciju, dimenzije i rashladni učinak i vraća
    rečnik {kolona prečišćene baze: broj}, bez polja koja nisu pronađena.
    """
    rezultat = {}

    # za svaku kolonu uzimam prvi sinonim sa pravom jedinicom i vrednošću u opsegu;
    # isti naziv ume da ima više vrednosti, pa ih probam redom, a raspon iz filtera
    # preskačem; break prekida probanje čim nađem dobru vrednost
    for polje, (nazivi, jedinica) in pravila.SINONIMI.items():
        for naziv in nazivi:
            for tekst in mapa.get(naziv, []):
                if pravila.OPSEG_RE.match(normalizuj(tekst)):
                    continue
                vrednost = u_opsegu(polje, izvuci_vrednost(tekst, jedinica), vrsta)
                if vrednost is not None:
                    rezultat[polje] = vrednost
                    break
            if polje in rezultat:
                break

    # rezoluciju '1920 x 1080 px' delim na dve kolone iz jednog polja: prvi broj je
    # širina, a drugi visina, i svaki posebno proveravam u opsegu
    for naziv in pravila.NAZIVI_REZOLUCIJE:
        if naziv in mapa:
            pogodak = REZOLUCIJA_RE.search(mapa[naziv][0])
            if pogodak:
                rezultat["rezolucija_sirina_px"] = u_opsegu("rezolucija_sirina_px", float(pogodak.group(1)))
                rezultat["rezolucija_visina_px"] = u_opsegu("rezolucija_visina_px", float(pogodak.group(2)))
                break

    # polje sa tri dimenzije ('60 x 85 x 60 cm') čitam u cm; kad naziv ili vrednost kažu
    # redosled ŠxVxD, popunjavam i širinu, visinu i dubinu koje sinonimi nisu našli
    for naziv in pravila.NAZIVI_DIMENZIJA:
        if naziv not in mapa:
            continue
        tekst = RAZMAK_U_BROJU_RE.sub(r"\1\2", normalizuj(mapa[naziv][0]))
        pogodak = DIMENZIJE_RE.search(tekst)
        if pogodak:
            # kad se u istoj vrednosti mešaju mm i cm, ne znam koji broj je u kojoj
            # jedinici, pa tu vrednost ne koristim
            if len({j for j in pogodak.group(2, 4, 6) if j}) > 1:
                continue
            mnozilac, brojevi = (0.1 if pogodak.group(6) == "mm" else 1.0), pogodak.group(1, 3, 5)
        else:
            # rezerva: prva tri broja iza kojih piše cm ('Visina: 85 cm, Širina: 60 cm, Dubina: 55 cm')
            mnozilac, brojevi = 1.0, CM_RE.findall(tekst)[:3]
        stranice = [u_broj(b) for b in brojevi]
        # tražim tri broja i da nijedan nije nula ili nečitljiv (None)
        if len(stranice) < 3 or not all(stranice):
            continue
        stranice = [round(s * mnozilac, 2) for s in stranice]
        if pogodak and ("sxvxd" in naziv or "sxvxd" in tekst):
            # redosled je poznat, pa popunjavam dimenzije, a gabarit se računa ispod iz njih
            for polje, stranica in zip(("sirina_cm", "visina_cm", "dubina_cm"), stranice):
                if polje not in rezultat:
                    rezultat[polje] = u_opsegu(polje, stranica, vrsta)
        else:
            # gabarit ne zavisi od redosleda dimenzija, pa ga računam i kad redosled ne piše
            rezultat["gabarit_cm3"] = u_opsegu("gabarit_cm3", round(stranice[0] * stranice[1] * stranice[2], 2))
        break

    # kad su poznate sve tri dimenzije, gabarit računam iz njih
    if all(rezultat.get(p) for p in ("visina_cm", "sirina_cm", "dubina_cm")):
        rezultat["gabarit_cm3"] = u_opsegu(
            "gabarit_cm3",
            round(rezultat["visina_cm"] * rezultat["sirina_cm"] * rezultat["dubina_cm"], 2))

    # rashladni učinak: kad mi je poznat samo kW ili samo BTU, drugi preračunam
    # po odnosu 1 kW ≈ 3412 BTU/h, da bi obe kolone bile popunjene
    if rezultat.get("kapacitet_hladjenja_kw") and not rezultat.get("kapacitet_hladjenja_btu"):
        rezultat["kapacitet_hladjenja_btu"] = u_opsegu(
            "kapacitet_hladjenja_btu", round(rezultat["kapacitet_hladjenja_kw"] * 3412))
    elif rezultat.get("kapacitet_hladjenja_btu") and not rezultat.get("kapacitet_hladjenja_kw"):
        rezultat["kapacitet_hladjenja_kw"] = u_opsegu(
            "kapacitet_hladjenja_kw", round(rezultat["kapacitet_hladjenja_btu"] / 3412, 2))

    # izbacujem ključeve koji su ispali iz opsega i ostali None
    return {k: v for k, v in rezultat.items() if v is not None}


def ima_oznaku_skale(sirovo: str | None) -> bool:
    """Vraća True kad tekst klase sam kaže skalu: 'Novo', 'po prethodnoj klasifikaciji' ili '+' u klasi."""
    if not sirovo:
        return False
    return bool(pravila.OZNAKA_NOVE_SKALE.search(sirovo) or pravila.OZNAKA_STARE_SKALE.search(sirovo)
                or "+" in sirovo)


def parsiraj_energetsku(sirovo: str | None, kategorija: str) -> tuple[str | None, str | None, int | None]:
    """
    Iz teksta energetske klase vadi klasu, skalu i rang unutar te skale
    (1 = najbolja). Izričita oznaka u tekstu ima prednost, a golo slovo
    tumačim po vrsti uređaja. Stara i nova skala se ne spajaju, pa rang ima
    smisla samo unutar svoje skale.

    Primeri:
        'A', 'frizider'                          → ('A',  'nova',  1)
        'A', 'rerna'                             → ('A',  'stara', 4)
        'A+ (po prethodnoj klasifikaciji)', ...  → ('A+', 'stara', 3)
        'F - Novo', ...                          → ('F',  'nova',  6)
    """
    if not sirovo:
        return None, None, None

    # tekst pretvaram u velika slova, da i 'a+' iz izvora prepoznam kao 'A+'
    pogodak = pravila.ENERGETSKA_KLASA_RE.search(sirovo.upper())
    if not pogodak:
        return None, None, None
    klasa = pogodak.group(1)

    # 1) staru skalu prepoznajem po oznaci ('po prethodnoj ...') ili po '+' u klasi, a novu po 'Novo';
    # 2) golo slovo je nova skala samo kod vrsta uređaja koje imaju novu nalepnicu
    if pravila.OZNAKA_STARE_SKALE.search(sirovo) or "+" in klasa:
        stara = True
    elif pravila.OZNAKA_NOVE_SKALE.search(sirovo):
        stara = False
    else:
        stara = kategorija not in pravila.KATEGORIJE_NOVE_SKALE
    skala = "stara" if stara else "nova"
    lestvica = pravila.STARA_SKALA if stara else pravila.NOVA_SKALA

    # index kreće od 0, pa dodajem 1 da najbolja klasa ima rang 1
    return klasa, skala, lestvica.index(klasa) + 1


def nadji_energetsku(mapa: dict[str, list[str]], kategorija: str) -> tuple:
    """
    Prolazi kroz nazive iz pravila.NAZIVI_ENERGETSKE_KLASE i sve njihove vrednosti
    i vraća (tekst, klasa, skala, rang) za prvu vrednost iz koje se klasa može
    pročitati. Prednost imaju vrednosti koje same kažu skalu ('A++', 'C - Novo').
    Uvoznikova lista ume da ima 'OA+++', pa se tada uzima sledeća vrednost.
    """
    # sve vrednosti skupljam u jednu listu, redom kojim probam nazive
    vrednosti = [tekst for naziv in pravila.NAZIVI_ENERGETSKE_KLASE for tekst in mapa.get(naziv, [])]
    # sortiranje je stabilno, pa vrednosti sa izričitom oznakom skale idu prve,
    # a ostale ostaju u istom redu; tako golo slovo ne preduhitri 'A++' ni 'C - Novo'
    for tekst in sorted(vrednosti, key=ima_oznaku_skale, reverse=True):
        klasa, skala, rang = parsiraj_energetsku(tekst, kategorija)
        if klasa:
            return tekst, klasa, skala, rang
    return None, None, None, None


# -------------------------------
# Korak 4: brend, model i ključ spajanja
# -------------------------------
def kljuc_brenda(brend: str | None) -> str:
    """
    Pravi ključ brenda: normalizovan tekst iz kog izbacuje sve što nije slovo
    ili cifra. Tako 'De Longhi', 'DeLonghi' i 'DE LONGHI' daju isti ključ
    'delonghi'. Za prazan brend vraća prazan string.
    """
    # posle normalizuj ostaju mala slova bez kvačica, pa brišem razmake, crtice i tačke
    return re.sub(r"[^a-z0-9]", "", normalizuj(brend)) if brend else ""


def napravi_recnik_brendova(zapisi: list[dict]) -> dict[str, str]:
    """
    Funkcija broji sve zapise brenda po ključu i vraća rečnik {ključ brenda:
    zapis za prikaz}. Bira najčešći zapis koji nije ceo velikim slovima
    ('KitchenAid', a ne Winwinov 'KITCHENAID'); ako takvog nema, uzima
    najčešći sa velikim početnim slovom, a kratke skraćenice ostavlja velikim.
    """
    # brojim koliko se puta javlja svaki zapis, grupisano po ključu brenda;
    # pre brojanja svodim razmake, da 'De  Longhi' i 'De Longhi' budu isti zapis
    po_kljucu: dict[str, Counter] = defaultdict(Counter)
    for zapis in zapisi:
        if zapis.get("brend"):
            po_kljucu[kljuc_brenda(zapis["brend"])][RAZMAK_RE.sub(" ", zapis["brend"].strip())] += 1

    recnik = {}
    for kljuc, zapisi_brenda in po_kljucu.items():
        # brend od samih znakova (npr. '-') daje prazan ključ i njega preskačem
        if not kljuc:
            continue
        # kratak ključ (do 3 znaka) je skraćenica, pa uzimam zapis velikim slovima
        # (LG, TCL, AEG); inače bi title() od 'LG' napravio 'Lg'
        velikim_slovima = [zapis for zapis in zapisi_brenda if zapis.isupper()]
        if len(kljuc) <= 3 and velikim_slovima:
            recnik[kljuc] = velikim_slovima[0]
            continue
        # pravim parove (broj, zapis), pa mi max bira zapis koji se najčešće javlja;
        # ako su svi zapisi velikim slovima, najčešći pretvaram u oblik 'Gorenje'
        mesoviti = [(broj, zapis) for zapis, broj in zapisi_brenda.items() if not zapis.isupper()]
        if mesoviti:
            recnik[kljuc] = max(mesoviti)[1]
        else:
            recnik[kljuc] = max(zapisi_brenda.items(), key=lambda par: par[1])[0].title()
    return recnik


def izvuci_model(mapa: dict[str, list[str]], naziv: str, brend: str | None) -> str | None:
    """
    Vraća oznaku modela ili None. Prvo gleda karakteristiku 'Model' (dužine
    2 do 60 znakova), a ako je nema, iz naziva izbacuje brend i uzima najduži
    deo od bar 4 znaka koji ima i slovo i cifru ('NRK61JSY2W', 'HD9280-90').
    """
    # 1) prvo gledam karakteristiku koju je prodavnica sama izdvojila; vrednost
    #    kraću od 2 ili dužu od 60 znakova preskačem
    for naziv_atributa in pravila.NAZIV_ATRIBUTA_MODEL:
        if naziv_atributa in mapa:
            vrednost = RAZMAK_RE.sub(" ", mapa[naziv_atributa][0].strip())
            if 2 <= len(vrednost) <= 60:
                return vrednost

    # 2) iz naziva brišem brend, da se ime brenda ne bi uzelo kao model
    tekst = naziv
    if brend:
        tekst = re.sub(re.escape(brend), " ", tekst, flags=re.IGNORECASE)

    # naziv delim po razmacima, zarezima i zagradama i zadržavam delove sa slovom i cifrom
    kandidati = [d for d in re.split(r"[\s,;()]+", tekst)
                 if re.search(r"\d", d) and re.search(r"[A-Za-z]", d) and len(d) >= 4]
    return max(kandidati, key=len) if kandidati else None


def kljuc_spajanja(brend: str, model: str | None, naziv: str) -> str:
    """
    Pravi ključ 'brend|model' po kome se isti uređaj prepoznaje u više
    prodavnica; kad modela nema, umesto njega ide naziv. Izbacuje sve što nije
    slovo ili cifra, pa 'NRK-61 JSY2W' i 'NRK61JSY2W' daju isti ključ.
    """
    osnova = model if model else naziv
    # oba dela čistim isto kao u kljuc_brenda, a uspravna crta ih razdvaja
    deo_brenda = kljuc_brenda(brend)
    deo_modela = re.sub(r"[^a-z0-9]", "", normalizuj(osnova))
    # Winwin u karakteristici 'Model' često piše i brend ('Gorenje NRK619DA2XL4'), a
    # Gigatron ne ('NRK619DA2XL4'), pa brend sa početka modela skidam da ključevi budu isti
    if deo_brenda and deo_modela.startswith(deo_brenda) and len(deo_modela) > len(deo_brenda):
        deo_modela = deo_modela[len(deo_brenda):]
    return deo_brenda + "|" + deo_modela


def delovi_naziva(naziv: str) -> tuple:
    """
    Vraća grupe slova i grupe cifara iz naziva, poređane po abecedi. Tako
    'BEKO CFB 6432 XG Aspirator' i 'Beko Aspirator CFB6432XG' daju isto, jer se
    razlikuju samo po razmacima i po redosledu reči.
    """
    return tuple(sorted(re.findall(r"[a-z]+|[0-9]+", normalizuj(naziv))))


def oznake_u_nazivu(naziv: str) -> set[str]:
    """
    Vraća sve oznake modela koje se iz naziva mogu pročitati kao niz celih reči
    bez razmaka; npr. za 'BEKO RFNE 290 L41 WN Zamrzivač' među njima je 'rfne290l41wn'.
    Oznaka mora da ima bar 5 znakova, i slovo i cifru, a reč iza nje ne sme da
    bude nastavak oznake (reč sa cifrom, do tri slova ili znak '+'), jer 'KG 3330'
    nije isti frižider kao 'KG 3330 SE', a 'ACP-12CH35AERI' nije ista klima kao
    'ACP-12CH35AERI+'.
    """
    # znak '+' čuvam kao posebnu reč, jer je i on nastavak oznake
    reci = re.findall(r"[a-z0-9]+|\+", normalizuj(naziv))
    oznake = set()
    # i je prva, a j - 1 poslednja reč oznake; reč iza oznake je reci[j]
    for i in range(len(reci)):
        for j in range(i + 1, len(reci) + 1):
            oznaka = "".join(reci[i:j])
            posle = reci[j] if j < len(reci) else ""
            if (len(oznaka) >= 5 and re.search(r"\d", oznaka) and re.search(r"[a-z]", oznaka)
                    and not re.search(r"\d", posle) and (posle == "" or len(posle) > 3)):
                oznake.add(oznaka)
    return oznake


# -------------------------------
# Učitavanje primarne baze
# -------------------------------
def ucitaj_primarne() -> tuple[list[dict], dict[int, dict[str, list[str]]]]:
    """
    Učitava sve proizvode (sa šifrom prodavnice) i sve karakteristike iz
    primarne baze. Vraća listu proizvoda i rečnik {proizvod_id: {normalizovan
    naziv karakteristike: lista vrednosti}}.
    """
    # JOIN sa prodavnicama radim da bih uz svaki proizvod imala šifru prodavnice,
    # koja mi treba za izvore i tabelu poreklo. Oba upita ređam po id-u, jer bez
    # ORDER BY baza sme da vrati redove u bilo kom redosledu, a od redosleda zavise
    # id-evi u prečišćenoj bazi i to koja je „prva vrednost" jedne karakteristike.
    with veza("primarna") as konekcija:
        with konekcija.cursor() as kurzor:
            kurzor.execute("""
                SELECT  p.id, pr.sifra, p.url, p.naziv, p.brend, p.kategorija,
                        p.kategorija_puna, p.cena, p.na_stanju, p.ocena, p.broj_ocena
                FROM        primarna.proizvodi  p
                JOIN        primarna.prodavnice pr ON pr.id = p.prodavnica_id
                ORDER BY    p.id
            """)
            # iz kurzor.description uzimam imena kolona, pa svaki red pretvaram u rečnik
            kolone = [o[0] for o in kurzor.description]
            proizvodi = [dict(zip(kolone, red)) for red in kurzor.fetchall()]

            # ORDER BY id mi daje karakteristike istim redom kojim ih je parser upisao
            kurzor.execute("SELECT proizvod_id, naziv, vrednost FROM primarna.karakteristike "
                           "ORDER BY proizvod_id, id")
            # nazive karakteristika normalizujem odmah, da odgovaraju nazivima iz pravila.SINONIMI
            karakteristike = defaultdict(dict)
            sifra_prodavnice = {zapis["id"]: zapis["sifra"] for zapis in proizvodi}
            for proizvod_id, naziv, vrednost in kurzor.fetchall():
                kljuc = normalizuj(naziv)
                # šablonsku vrednost iz tabele filtera preskačem, pa ostaje sledeća vrednost tog naziva
                if (kljuc, vrednost) in pravila.SABLONSKE_VREDNOSTI.get(sifra_prodavnice.get(proizvod_id), ()):
                    continue
                # čuvam sve vrednosti istog naziva redom kojim ih je parser upisao; za Winwin je
                # prva iz uvoznikove specifikacije, a posle nje dolaze redovi tabele filtera
                karakteristike[proizvod_id].setdefault(kljuc, []).append(vrednost)

    return proizvodi, karakteristike


# -------------------------------
# Glavna obrada
# -------------------------------
def broj_izvornih_polja(polja: dict) -> int:
    """
    Broji popunjena tehnička polja bez energetske klase, a ne broji ono što je
    izračunato iz drugih polja: rashladni učinak u kW i BTU je isti podatak u dve
    jedinice, a gabarit je proizvod tri dimenzije koje su već prebrojane.
    """
    kolone = set(polja) - {"energetska_klasa", "energetska_skala", "energetska_klasa_num"}
    broj = len(kolone)
    # za svaku grupu kolona u kojoj je jedna izvedena iz ostalih oduzimam po jedno polje
    for isti_podatak in ({"kapacitet_hladjenja_kw", "kapacitet_hladjenja_btu"},
                         {"visina_cm", "sirina_cm", "dubina_cm", "gabarit_cm3"}):
        if isti_podatak <= kolone:
            broj -= 1
    return broj


def obradi(min_karakteristika: int) -> None:
    """
    Funkcija učitava primarnu bazu, filtrira i tipizira svaki zapis, spaja
    duplikate po (ključ spajanja, kategorija) i po nazivu, računa izvedene
    pokazatelje, upisuje sve u prečišćenu bazu i na kraju ispisuje dnevnik po
    koracima.
    """
    # pamtim vreme početka za izveštaj, a u dnevnik brojim zapise po koracima
    pocetak = time.perf_counter()
    dnevnik = Counter()

    print("[INFO] Učitavam primarnu bazu...")
    proizvodi, karakteristike = ucitaj_primarne()
    dnevnik["ucitano iz primarne baze"] = len(proizvodi)
    print(f"[INFO] Učitano {len(proizvodi):,} zapisa i "
          f"{sum(len(v) for v in karakteristike.values()):,} karakteristika")

    # brendove ujednačavam pre petlje, jer od ujednačenog brenda zavisi ključ spajanja,
    # pa 'DeLonghi' i 'De Longhi' iz dve prodavnice upadnu u istu grupu
    recnik_brendova = napravi_recnik_brendova(proizvodi)
    # skup mi daje broj različitih zapisa brenda pre ujednačavanja, samo za ispis
    razlicitih_zapisa = len({z["brend"] for z in proizvodi if z.get("brend")})
    print(f"[INFO] Brendovi: {razlicitih_zapisa} različitih zapisa svedeno na "
          f"{len(recnik_brendova)} proizvođača")

    # u grupe skupljam sve zapise istog uređaja pod (ključ spajanja, kategorija), a u
    # nepoznate_kategorije brojim nazive kategorija koje nisam prepoznala
    grupe: dict[tuple[str, str], list[dict]] = defaultdict(list)
    nepoznate_kategorije = Counter()

    for zapis in proizvodi:
        # zapis bez cene odbacujem ceo i to beležim u dnevnik
        if zapis["cena"] is None:
            dnevnik["odbačeno: bez cene"] += 1
            continue

        # korak 1: kategorija; odbačene brojim da bih videla da nije nešto propušteno
        odredjena = odredi_kategoriju(zapis["kategorija"], zapis["kategorija_puna"], zapis["naziv"])
        if not odredjena:
            dnevnik["odbačeno: kategorija nije bela tehnika"] += 1
            nepoznate_kategorije[zapis["kategorija"] or "(prazno)"] += 1
            continue
        kategorija, grupa = odredjena

        # opseg cene proveravam tek kad znam vrstu uređaja, jer aspirator od 499 dinara
        # jeste greška, a kuvalo od 699 dinara nije
        if not u_opsegu("cena", float(zapis["cena"]), (kategorija, grupa)):
            dnevnik["odbačeno: cena van opsega"] += 1
            continue

        # pribor koji sajt drži među uređajima (filter, nastavak, grejna fioka) prepoznajem po nazivu
        if any(re.search(obrazac, normalizuj(zapis["naziv"])) for obrazac in pravila.NAZIVI_ZA_IZBACIVANJE):
            dnevnik["odbačeno: pribor po nazivu"] += 1
            continue

        # brend u ujednačenom obliku; zapis bez brenda ne može da dobije ključ spajanja
        brend = recnik_brendova.get(kljuc_brenda(zapis["brend"]))
        if not brend:
            dnevnik["odbačeno: bez brenda"] += 1
            continue

        # korak 2 i 3: vadim brojeve iz karakteristika i energetsku klasu (nazivi su već normalizovani);
        # tri polja klase dodajem samo kad je klasa pronađena
        mapa = karakteristike.get(zapis["id"], {})
        polja = tipiziraj_karakteristike(mapa, (kategorija, grupa))

        # tri polja klase i podatak da li tekst sam kaže skalu čuvam posebno, za izbor pri spajanju
        sirova_klasa, klasa, skala, rang = nadji_energetsku(mapa, kategorija)
        energija = {}
        if klasa:
            energija = {"energetska_klasa": klasa, "energetska_skala": skala,
                        "energetska_klasa_num": rang}

        # korak 4: model i ključ; isti ključ u različitim kategorijama ostavljam odvojen
        model = izvuci_model(mapa, zapis["naziv"], brend)
        kljuc = kljuc_spajanja(brend, model, zapis["naziv"])
        # outlet oglas je sniženi primerak, pa ga ne spajam sa redovnim oglasom istog modela
        if "outlet" in normalizuj(zapis["naziv"]):
            kljuc += "|outlet"

        # u grupu dodajem kopiju zapisa sa ujednačenim brendom, modelom i kategorijom
        grupe[(kljuc, kategorija)].append({
            **zapis, "brend": brend, "model": model, "kategorija": kategorija,
            "kategorija_izvorna": zapis["kategorija"],      # kako je pisalo na sajtu
            "grupa": grupa, "polja": polja,
            "energija": energija, "izricita_skala": ima_oznaku_skale(sirova_klasa),
        })

    print(f"[INFO] Posle filtriranja ostalo {sum(len(v) for v in grupe.values()):,} zapisa "
          f"u {len(grupe):,} grupa")

    # --- Korak 4a: dva oglasa iste prodavnice pod istim ključem ---
    # Kad grupa ima dva oglasa iste prodavnice sa različitim delovima naziva, to je
    # najčešće drugi model, druga boja ili ponuda sa ugradnjom, koje ključ nije razlikovao
    # (npr. Winwin i kod TCL 98C735 u 'Model' piše '43C735 Smart'). Takvu grupu delim:
    # svaki zapis dobija ključ iz svog naziva, kao zapis bez modela. Oglas druge
    # prodavnice iz te grupe posle toga može da nađe svoj par u koraku 4b.
    for (kljuc, kategorija), zapisi in list(grupe.items()):
        # kad parova (prodavnica, delovi naziva) ima više nego prodavnica, neka
        # prodavnica u grupi ima oglase sa dva različita naziva
        nazivi = {(z["sifra"], delovi_naziva(z["naziv"])) for z in zapisi}
        if len(nazivi) > len({z["sifra"] for z in zapisi}):
            del grupe[(kljuc, kategorija)]
            for zapis in zapisi:
                grupe[(kljuc_spajanja(zapis["brend"], None, zapis["naziv"]), kategorija)].append(zapis)

    # --- Korak 4b: isti uređaj pod dva ključa ---
    # Gigatron u karakteristiku 'Model' ume da upiše svoju internu šifru (ELE00424, 734819)
    # ili je ne upiše, pa isti uređaj iz dve prodavnice dobije dva ključa. Zato Gigatron
    # grupu tražim među Winwin grupama iste kategorije: po istim delovima naziva ili po
    # Winwin modelu koji se vidi u Gigatron nazivu. Gledam samo grupe sa jednim oglasom,
    # jer grupa sa dva oglasa iste prodavnice ume da drži dve varijante uređaja, a outlet
    # oglas ne spajam sa redovnim.
    # Winwin grupe sa jednim oglasom pamtim na dva mesta: po delovima naziva i po modelu iz ključa
    po_nazivu, po_modelu = defaultdict(set), defaultdict(set)
    for (kljuc, kategorija), zapisi in grupe.items():
        if [z["sifra"] for z in zapisi] == ["winwin"]:
            brend, model = kljuc.split("|", 1)
            po_nazivu[(kategorija, delovi_naziva(zapisi[0]["naziv"]))].add((kljuc, kategorija))
            po_modelu[(kategorija, brend, model)].add((kljuc, kategorija))
    parovi = {}
    for (kljuc, kategorija), zapisi in grupe.items():
        naziv = zapisi[0]["naziv"]
        if [z["sifra"] for z in zapisi] != ["gigatron"] or "outlet" in normalizuj(naziv):
            continue
        brend = kljuc.split("|")[0]
        kandidati = set(po_nazivu.get((kategorija, delovi_naziva(naziv)), set()))
        for oznaka in oznake_u_nazivu(naziv):
            kandidati |= po_modelu.get((kategorija, brend, oznaka), set())
        # par pamtim samo kad je Gigatron grupa našla tačno jednu Winwin grupu
        if len(kandidati) == 1:
            parovi[(kljuc, kategorija)] = kandidati.pop()
    # i spajam ga samo ako tu Winwin grupu nije našla nijedna druga Gigatron grupa
    koliko = Counter(parovi.values())
    for gigatron_grupa, winwin_grupa in parovi.items():
        if koliko[winwin_grupa] == 1:
            grupe[winwin_grupa].extend(grupe.pop(gigatron_grupa))

    # --- Korak 5: spajanje duplikata ---
    redovi, poreklo_svih = [], []
    for (kljuc, kategorija), zapisi in grupe.items():
        # vodeći je zapis sa najviše popunjenih polja; setdefault zadržava njegove
        # vrednosti, a polja koja mu fale dopunjuje iz ostalih zapisa iste grupe
        zapisi.sort(key=lambda z: len(z["polja"]), reverse=True)
        vodeci = zapisi[0]

        spojena_polja = {}
        for zapis in zapisi:
            for polje, vrednost in zapis["polja"].items():
                spojena_polja.setdefault(polje, vrednost)

        # energetsku klasu uzimam iz zapisa čiji tekst sam kaže skalu ('Novo', 'po prethodnoj',
        # '+'), a ako takvog nema, iz prvog zapisa koji klasu ima (vodeći je prvi); kad dva
        # zapisa izričito tvrde različite skale, prednost ima skala koja odgovara vrsti uređaja
        sa_klasom = [z for z in zapisi if z["energija"]]
        if sa_klasom:
            izricite = [z for z in sa_klasom if z["izricita_skala"]] or sa_klasom
            ocekivana = "nova" if kategorija in pravila.KATEGORIJE_NOVE_SKALE else "stara"
            izabran = next((z for z in izricite if z["energija"]["energetska_skala"] == ocekivana), izricite[0])
            spojena_polja.update(izabran["energija"])

        # iz svih zapisa grupe skupljam cene, šifre prodavnica i poznate dostupnosti
        cene = [float(z["cena"]) for z in zapisi if z["cena"] is not None]
        izvori = sorted({z["sifra"] for z in zapisi})
        poznata_stanja = [z["na_stanju"] for z in zapisi if z["na_stanju"] is not None]
        # u prag brojim samo podatke pročitane iz izvora, bez energetske klase
        broj_tehnickih = broj_izvornih_polja(spojena_polja)

        # grupu sa premalo tehničkih polja izbacujem sa svim njenim zapisima
        if broj_tehnickih < min_karakteristika:
            dnevnik["odbačeno: premalo popunjenih karakteristika"] += len(zapisi)
            continue

        # od n zapisa u grupi ostaje jedan red, pa kao spojene brojim n - 1
        if len(zapisi) > 1:
            dnevnik["spojenih zapisa u duplikate"] += len(zapisi) - 1

        # sve kolone iz POLJA_PRECISCENE prvo postavim na None, a spojena polja ih prepisuju;
        # razliku u ceni računam u procentima u odnosu na najnižu cenu
        red = {
            "brend":              vodeci["brend"],
            # model uzimam iz zapisa čiji je model dao ključ reda, jer vodeći Gigatron zapis
            # ume da ima internu šifru ili da nema model; ako takvog nema, uzimam model vodećeg
            "model":              next((z["model"] for z in zapisi if z["model"] and
                                        kljuc_spajanja(z["brend"], z["model"], z["naziv"]) == kljuc),
                                       vodeci["model"]),
            "naziv":              vodeci["naziv"],
            "kljuc_spajanja":     kljuc,
            "kategorija":         kategorija,
            "kategorija_izvorna": vodeci["kategorija_izvorna"],
            "grupa":              vodeci["grupa"],
            "cena_min":           min(cene),
            "cena_max":           max(cene),
            "cena_prosek":        round(sum(cene) / len(cene), 2),
            "razlika_cene_procenat": round((max(cene) - min(cene)) / min(cene) * 100, 2) if min(cene) else None,
            "broj_prodavnica":    len(izvori),
            "izvori":             ",".join(izvori),
            # True ako je na stanju bar u jednoj prodavnici, False ako se zna da ga
            # nema nigde, a None kad dostupnost nije poznata ni u jednoj
            "na_stanju":          any(poznata_stanja) if poznata_stanja else None,
            # ocenu i broj ocena uzimam iz prvog zapisa grupe koji ih ima
            "ocena":              next((float(z["ocena"]) for z in zapisi if z["ocena"]), None),
            "broj_ocena":         next((z["broj_ocena"] for z in zapisi if z["broj_ocena"]), None),
            "broj_karakteristika": broj_tehnickih,
            **{polje: None for polje in POLJA_PRECISCENE},
            **spojena_polja,
        }

        # --- Korak 6: izvedeni pokazatelji ---
        # najnižu cenu delim veličinom uređaja, samo kad je veličina poznata,
        # da ne bih delila nulom ili sa None
        red["cena_po_incu"] = (round(red["cena_min"] / red["dijagonala_inch"], 2)
                               if red.get("dijagonala_inch") else None)
        red["cena_po_litru"] = (round(red["cena_min"] / red["zapremina_l"], 2)
                                if red.get("zapremina_l") else None)
        red["cena_po_kg_kapaciteta"] = (round(red["cena_min"] / red["kapacitet_pranja_kg"], 2)
                                        if red.get("kapacitet_pranja_kg") else None)
        red["cena_po_kw_hladjenja"] = (round(red["cena_min"] / red["kapacitet_hladjenja_kw"], 2)
                                       if red.get("kapacitet_hladjenja_kw") else None)

        # uz red pamtim i sve izvorne zapise, za tabelu poreklo
        redovi.append(red)
        poreklo_svih.append([(z["id"], z["sifra"], z["url"], z["cena"]) for z in zapisi])

    # broj upisanih stavljam u dnevnik pre upisa, da bi i on završio u tabeli dnevnik_ciscenja
    dnevnik["upisano u prečišćenu bazu"] = len(redovi)
    upisi(redovi, poreklo_svih, dnevnik)

    # --- Izveštaj ---
    # ispisujem trajanje i korake dnevnika od najvećeg broja zapisa ka najmanjem
    minuti = (time.perf_counter() - pocetak) / 60
    print(f"\n[OK] Prečišćena baza napravljena za {minuti:.1f} min")
    print(f"       {'korak':45} {'zapisa':>10}")
    for korak, broj in dnevnik.most_common():
        print(f"       {korak:45} {broj:>10,}")

    # deset najčešćih odbačenih kategorija ispisujem da ručno proverim pravila
    if nepoznate_kategorije:
        print("\n[INFO] Najčešće odbačene kategorije (provera da nije nešto propušteno):")
        for naziv, broj in nepoznate_kategorije.most_common(10):
            print(f"         {naziv:45} {broj:>6,}")


# kolone koje dolaze iz karakteristika (energetska klasa i tehnička polja);
# svaki red ih dobija sve, pa za podatak koji ne postoji upisujem NULL.
# Liste su ispod obradi(), ali to ne smeta, jer ih čitam tek kad se funkcija pozove.
POLJA_PRECISCENE = [
    "energetska_klasa", "energetska_skala", "energetska_klasa_num",
    "dijagonala_inch", "rezolucija_sirina_px", "rezolucija_visina_px",
    "zapremina_l", "zapremina_frizider_l", "zapremina_zamrzivac_l",
    "kapacitet_pranja_kg", "kapacitet_kompleta", "brzina_centrifuge",
    "snaga_w", "kapacitet_hladjenja_btu", "kapacitet_hladjenja_kw",
    "visina_cm", "sirina_cm", "dubina_cm", "tezina_kg", "nivo_buke_db",
    "potrosnja_kwh", "broj_programa", "broj_brzina", "gabarit_cm3",
]

# sve kolone koje upisujem u preciscena.proizvodi; iz ove liste upisi() gradi INSERT upit
SVE_KOLONE = [
    "brend", "model", "naziv", "kljuc_spajanja", "kategorija", "kategorija_izvorna",
    "grupa", "cena_min", "cena_max", "cena_prosek", "razlika_cene_procenat",
    "broj_prodavnica", "izvori", "na_stanju", "ocena", "broj_ocena",
    *POLJA_PRECISCENE,
    "cena_po_incu", "cena_po_litru", "cena_po_kg_kapaciteta", "cena_po_kw_hladjenja",
    "broj_karakteristika",
]


def upisi(redovi: list[dict], poreklo_svih: list[list], dnevnik: Counter) -> None:
    """
    Prazni tri tabele prečišćene baze, pa upisuje svaki proizvod, uz njega
    zapise iz kojih je nastao (poreklo) i na kraju dnevnik čišćenja.
    """
    print(f"[INFO] Upisujem {len(redovi):,} prečišćenih proizvoda...")
    # upit gradim iz SVE_KOLONE sa imenovanim parametrima %(kolona)s, pa mi red kao
    # rečnik sam popuni vrednosti i ne moram da pazim na redosled
    upit = (f"INSERT INTO preciscena.proizvodi ({', '.join(SVE_KOLONE)}) "
            f"VALUES ({', '.join('%(' + k + ')s' for k in SVE_KOLONE)}) RETURNING id")

    with veza("preciscena") as konekcija:
        with konekcija.cursor() as kurzor:
            # bazu punim ispočetka: TRUNCATE briše stare redove, a RESTART IDENTITY vraća id na 1
            kurzor.execute("TRUNCATE preciscena.proizvodi, preciscena.poreklo, "
                           "preciscena.dnevnik_ciscenja RESTART IDENTITY CASCADE")

            # RETURNING id mi vraća novi id proizvoda, koji mi treba za redove u poreklo;
            # sve izvorne zapise jednog proizvoda upisujem odjednom preko executemany
            for red, poreklo in zip(redovi, poreklo_svih):
                kurzor.execute(upit, {k: red.get(k) for k in SVE_KOLONE})
                novi_id = kurzor.fetchone()[0]
                kurzor.executemany(
                    """INSERT INTO preciscena.poreklo (preciscen_id, primarni_id, prodavnica, url, cena)
                       VALUES (%s, %s, %s, %s, %s)""",
                    [(novi_id, *stavka) for stavka in poreklo])

            # na kraju upisujem dnevnik kao parove (korak, broj zapisa)
            kurzor.executemany(
                "INSERT INTO preciscena.dnevnik_ciscenja (korak, broj_zapisa) VALUES (%s, %s)",
                list(dnevnik.items()))


def main() -> None:
    """Čita opciju --min_karakteristika i pokreće obradu."""
    # podrazumevanu granicu uzimam iz pravila.MINIMALNO_KARAKTERISTIKA, a opcijom je menjam
    parser = argparse.ArgumentParser(description="Preprocesiranje i formiranje prečišćene baze.")
    parser.add_argument("--min_karakteristika", type=int, default=pravila.MINIMALNO_KARAKTERISTIKA,
                        help="najmanji broj popunjenih tehničkih polja da zapis uđe u bazu")
    argumenti = parser.parse_args()
    obradi(argumenti.min_karakteristika)


if __name__ == "__main__":
    main()
