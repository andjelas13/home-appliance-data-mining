#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — Aplikacija sa prozorom za predviđanje cene, klasterovanje i preporuke (zadaci 4, 5 i 6).

Opis:
Prozor (tkinter, deo standardnog Python-a) ima tri kartice: predviđanje cene
(Zadatak 4), klasterovanje (Zadatak 5) i preporuke (Zadatak 6).
Model cene se ovde ne obučava, nego se učitava iz regresija_model.json.
Klasterovanje se računa pri svakom pokretanju, jer zavisi od izbora korisnika.
Profili za preporuke se grade jednom, pri pokretanju. Grafikoni se crtaju
matplotlib-om direktno u prozor.

Ulazi:
    prečišćena baza, tabela preciscena.proizvodi (preko podaci.py): PostgreSQL,
    MySQL ili kopija u fajlu baza/sqlite/psz_preciscena.sqlite (vidi zajednicko/baza.py)
    izvestaj/modeli/regresija_model.json (pravi ga models/regresija.py)

Izlazi:
    prozor aplikacije; aplikacija samo čita, ništa ne upisuje u bazu

Primer poziva:
    python kod/app/app.py
    (ili korak aplikacija iz pokreni.bat; na računaru bez PostgreSQL servera kod/pokreni_aplikaciju.py)
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

# kad izlaz nije konzola (npr. preusmeren u fajl), Windows ispisuje u kodnoj strani bez č i ć,
# pa bi print pukao; zato izlaz prebacujem na UTF-8. IDLE to ne podržava, pa ga preskačem.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


def proveri_biblioteke() -> None:
    """Proverava da Python ima biblioteke iz kod/requirements.txt koje prozor koristi; bez njih se ne otvara."""
    nedostaje = []
    for ime in ["numpy", "pandas", "matplotlib", "tkinter"]:
        try:
            importlib.import_module(ime)
        except ImportError:
            nedostaje.append(ime)
    if nedostaje:
        print(f"[GRESKA] Nije instalirano: {', '.join(nedostaje)}. Spisak biblioteka je u kod/requirements.txt "
              "(instalacija: pip install -r requirements.txt iz foldera kod).")
        sys.exit(1)


# proveru zovem pre uvoza biblioteka, da umesto duge greške Python-a piše šta fali
proveri_biblioteke()

import tkinter as tk
from tkinter import ttk

# TkAgg sam izabrala da matplotlib crta pravo u tkinter prozor
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
import pandas as pd

# dodajem folder models (podaci, regresija, kmeans, preporuke) i folder kod (paket zajednicko)
sys.path.append(str(Path(__file__).resolve().parents[1] / "models"))
sys.path.append(str(Path(__file__).resolve().parents[1]))

# ovde uvozim svoje module: pripremu podataka, predikciju cene, k-means i preporuke
from podaci import Priprema, ucitaj_preciscene
from regresija import dodaj_slobodni_clan, predvidi, decimalni
import kmeans as kmeans_modul
from preporuke import SistemPreporuka
from zajednicko import nazivi
from zajednicko.putanje import FOLDER_MODELA

# model cene čitam iz JSON fajla koji mi zapiše regresija.py posle obučavanja
PUTANJA_MODELA = FOLDER_MODELA / "regresija_model.json"

# boje prozora: bordo za naslove, zaglavlja i dugmad, svetla podloga za ostalo
BORDO = "#7a1f3d"
SVETLO = "#f3e6eb"
POZADINA = "#faf6f7"
TEKST = "#2b2024"
CRVENA = "#b3261e"
ROZE = "#e9b8c8"

# Polja forme za predviđanje cene: (kolona, naziv u prozoru, jedinica).
# Pazila sam da prate listu NUMERICKE iz podaci.py, inače matrica nema isti broj kolona
# kao θ. Kolone gabarit_cm3 i energetska_rang nisam stavila ovde, njih računam iz forme.
POLJA_FORME = [
    ("dijagonala_inch",        "Dijagonala ekrana", "inč"),
    ("zapremina_l",            "Ukupna zapremina", "l"),
    ("zapremina_frizider_l",   "Zapremina frižidera", "l"),
    ("zapremina_zamrzivac_l",  "Zapremina zamrzivača", "l"),
    ("kapacitet_pranja_kg",    "Kapacitet pranja", "kg"),
    ("kapacitet_kompleta",     "Kapacitet", "kompleta"),
    ("brzina_centrifuge",      "Brzina centrifuge", "obr/min"),
    ("snaga_w",                "Snaga", "W"),
    ("kapacitet_hladjenja_kw", "Rashladni učinak", "kW"),
    ("visina_cm",              "Visina", "cm"),
    ("sirina_cm",              "Širina", "cm"),
    ("dubina_cm",              "Dubina", "cm"),
    ("tezina_kg",              "Težina", "kg"),
    ("nivo_buke_db",           "Nivo buke", "dB"),
    ("broj_programa",          "Broj programa", ""),
]


# ============================================================================
# Učitavanje podataka i modela — jednom, pri pokretanju
# ============================================================================
class Stanje:
    """
    Čuva tabelu proizvoda, spiskove za padajuće menije, model cene i sistem
    preporuka, da se ne učitavaju pri svakom računanju.
    """

    def __init__(self):
        """
        Učitava prečišćenu bazu, pravi spiskove kategorija, brendova i
        energetskih klasa, učitava model cene i gradi profile za preporuke.
        """
        print("[INFO] Učitavam prečišćenu bazu...")
        self.tabela = ucitaj_preciscene()

        # spiskove za padajuće menije pravim iz jedinstvenih vrednosti, bez praznih, po abecedi
        self.kategorije = sorted(self.tabela["kategorija"].dropna().unique())
        self.brendovi = sorted(self.tabela["brend"].dropna().unique())
        # Za formu cene pamtim najmanju i najveću vrednost svake karakteristike po kategoriji i
        # raspon cena u bazi. Van tog opsega model samo produžava pravu daleko van podataka na
        # kojima je učio. Uz polja forme merim i gabarit, iz tri dimenzije, kao što ga i forma računa.
        kolone_forme = [naziv for naziv, _, _ in POLJA_FORME]
        mere = self.tabela[["kategorija"] + kolone_forme].copy()
        mere["gabarit_cm3"] = self.tabela["visina_cm"] * self.tabela["sirina_cm"] * self.tabela["dubina_cm"]
        self.najvece_vrednosti = mere.groupby("kategorija").max()
        self.najmanje_vrednosti = mere.groupby("kategorija").min()
        self.raspon_cena = (float(self.tabela["cena_min"].min()), float(self.tabela["cena_min"].max()))
        # Klasu nudim zajedno sa skalom, npr. „A (nova skala)“ i „A (prethodna klasifikacija)“,
        # jer to nisu isti nivo efikasnosti ni isti rang u modelu. Vrednost opcije mi je „klasa|skala“.
        klase = self.tabela.dropna(subset=["energetska_klasa", "energetska_klasa_num"])
        klase = (klase[klase["energetska_skala"].isin(["nova", "stara"])]
                 .drop_duplicates(["energetska_skala", "energetska_klasa"])
                 .sort_values(["energetska_skala", "energetska_klasa_num"]))
        self.energetske_klase = [
            {"vrednost": f"{red.energetska_klasa}|{red.energetska_skala}",
             "oznaka": f"{red.energetska_klasa} ({'nova skala' if red.energetska_skala == 'nova' else 'prethodna klasifikacija'})"}
            for red in klase.itertuples()]

        print("[INFO] Učitavam model za predviđanje cene...")
        self.model = self._ucitaj_model()

        # profile za preporuke gradim odmah, da kartica sa preporukama posle samo računa sličnost
        print("[INFO] Gradim profile za preporuke...")
        self.preporuke = SistemPreporuka(self.tabela)
        print(f"[OK] Spremno: {broj(len(self.tabela), 0)} proizvoda, "
              f"{len(self.preporuke.po_kategoriji)} kategorija sa preporukama")

    def _ucitaj_model(self) -> dict | None:
        """
        Čita regresija_model.json i vraća θ, podatak da li je model učio na
        logaritmu cene, naučenu pripremu i mere kvaliteta. Ako fajla nema, vraća None.
        """
        if not PUTANJA_MODELA.exists():
            print(f"[UPOZORENJE] Nema modela na {PUTANJA_MODELA}. Prvo pokreni: kod\\pokreni.bat regresija")
            return None
        zapis = json.loads(PUTANJA_MODELA.read_text(encoding="utf-8"))
        # θ vraćam u numpy niz, a pripremu obnavljam iz rečnika da imam iste medijane i skaliranje
        return {
            "theta":    np.array(zapis["theta"]),
            "log_cena": zapis["log_cena"],
            "priprema": Priprema.iz_recnika(zapis["priprema"]),
            "kvalitet": zapis["kvalitet"],
        }


# zajedničko stanje; pravim ga u dohvati_stanje(), pri prvom pozivu
stanje: Stanje | None = None


def dohvati_stanje() -> Stanje:
    """Vraća zajedničko stanje aplikacije, a pravi ga samo pri prvom pozivu."""
    global stanje
    if stanje is None:
        stanje = Stanje()
    return stanje


# ============================================================================
# Ispis brojeva
# ============================================================================
def dinari(vrednost) -> str:
    """Pretvara broj u cenu bez decimala, sa tačkom za hiljade i oznakom RSD; prazna vrednost je crtica."""
    if vrednost is None or (isinstance(vrednost, float) and pd.isna(vrednost)):
        return "—"
    # Python mi daje zarez za hiljade, a ja ga menjam tačkom kako se piše kod nas
    return f"{int(round(float(vrednost))):,}".replace(",", ".") + " RSD"


def broj(vrednost, decimala: int = 1) -> str:
    """Ispisuje broj sa zadatim brojem decimala, zarezom za decimale i tačkom za hiljade."""
    if vrednost is None or (isinstance(vrednost, float) and pd.isna(vrednost)):
        return "—"
    # zarez za hiljade privremeno menjam sa #, da se ne pomeša sa decimalnom tačkom koja postaje zarez
    return f"{float(vrednost):,.{decimala}f}".replace(",", "#").replace(".", ",").replace("#", ".")


# ============================================================================
# Zadatak 4 — predviđanje cene (računanje, bez prozora)
# ============================================================================
def proceni_cenu(unos: dict, s: Stanje) -> int:
    """
    Od unetih vrednosti pravi red, provlači ga kroz istu pripremu kao pri obučavanju
    i vraća procenjenu cenu u dinarima. Pogrešan unos javlja ValueError sa porukom.
    """
    if s.model is None:
        raise ValueError("Model nije obučen. Pokreni: kod\\pokreni.bat regresija")
    red = _napravi_red(unos, s)
    # ista priprema kao pri obučavanju (medijane, standardizacija, one-hot, interakcije),
    # pa dodajem kolonu jedinica za slobodni član θ₀
    X = dodaj_slobodni_clan(s.model["priprema"].primeni(red))
    vrednost = float(predvidi(X, s.model["theta"])[0])
    # ako je model učio na logaritmu cene, predikciju vraćam u dinare preko exp
    if s.model["log_cena"]:
        vrednost = float(np.exp(vrednost))
    # procenu van raspona cena iz baze ne prikazujem; ovo hvata i beskonačno i nulu
    najniza, najvisa = s.raspon_cena
    if not najniza <= vrednost <= najvisa:
        raise ValueError(f"Za unete vrednosti model daje cenu van raspona cena u bazi "
                         f"(od {dinari(najniza)} do {dinari(najvisa)}). Proveri vrednosti i jedinice.")
    return round(vrednost)


def _napravi_red(unos: dict, s: Stanje) -> pd.DataFrame:
    """
    Pravi tabelu sa jednim redom od unetih vrednosti. Prazna polja ostaju NaN, pa ih
    priprema popunjava medijanom kategorije (ili medijanom svih proizvoda, ako
    kategorija tu kolonu nema) i uključuje pokazatelj _nedostaje, isto kao pri obučavanju.
    """
    # kategoriju i brend primam samo ako su sa spiska, jer model zna samo te vrednosti
    red = {"kategorija": unos.get("kategorija"), "brend": unos.get("brend")}
    if red["kategorija"] not in s.kategorije or red["brend"] not in s.brendovi:
        raise ValueError("Izaberi kategoriju i brend sa spiska.")

    najvece = s.najvece_vrednosti.loc[red["kategorija"]]
    najmanje = s.najmanje_vrednosti.loc[red["kategorija"]]
    for naziv, opis, jedinica in POLJA_FORME:
        vrednost = str(unos.get(naziv, "") or "").strip()
        if not vrednost:
            red[naziv] = np.nan
            continue
        # „1.400“ bi se pročitalo kao 1,4, a „21.975“ kao 21,975 — tačka posle tačno tri cifre
        # je dvosmislena, pa tražim da broj bude upisan jednoznačno
        if re.fullmatch(r"[1-9]\d{0,2}(\.\d{3})+", vrednost):
            raise ValueError(f"Polje „{opis}“: tačka posle tri cifre je dvosmislena — hiljade piši "
                             f"bez tačke (1400), a decimale zarezom (21,975).")
        try:
            red[naziv] = float(vrednost.replace(",", "."))
        except ValueError:
            raise ValueError(f"Polje „{opis}“ mora biti broj.") from None
        if not np.isfinite(red[naziv]) or red[naziv] <= 0:
            raise ValueError(f"Polje „{opis}“ mora biti broj veći od nule.")
        # model je za ovu kategoriju učio samo na vrednostima iz baze, pa tražim da i unos bude u tom opsegu
        if pd.isna(najvece[naziv]):
            raise ValueError(f"Nijedan uređaj ove kategorije u bazi nema podatak „{opis}“, pa to polje ostavi prazno.")
        _proveri_opseg(red[naziv], f"Polje „{opis}“", jedinica, najmanje[naziv], najvece[naziv])

    # klasu primam samo sa spiska; prazno polje znači da klasa nije poznata i to je dozvoljeno
    izbor_klase = (unos.get("energetska_klasa") or "").strip()
    if izbor_klase and izbor_klase not in {opcija["vrednost"] for opcija in s.energetske_klase}:
        raise ValueError("Izaberi energetsku klasu sa spiska.")
    # iz „klasa|skala“ (npr. A|stara) rang tražim u bazi baš za tu klasu na toj skali
    klasa, _, skala = izbor_klase.partition("|")
    red["energetska_klasa"] = klasa or None
    podudarni = s.tabela[(s.tabela["energetska_klasa"] == klasa) & (s.tabela["energetska_skala"] == skala)]
    if klasa and podudarni["energetska_klasa_num"].notna().any():
        red["energetska_skala"] = skala
        red["energetska_rang"] = float(podudarni["energetska_klasa_num"].dropna().iloc[0])
    else:
        red["energetska_skala"] = "nepoznata"
        red["energetska_rang"] = np.nan

    # gabarit računam kao visina × širina × dubina, isto kao u ciscenje.py
    if all(not pd.isna(red.get(k)) for k in ("visina_cm", "sirina_cm", "dubina_cm")):
        red["gabarit_cm3"] = red["visina_cm"] * red["sirina_cm"] * red["dubina_cm"]
        _proveri_opseg(red["gabarit_cm3"], "Visina × širina × dubina", "cm³",
                       najmanje["gabarit_cm3"], najvece["gabarit_cm3"])
    else:
        red["gabarit_cm3"] = np.nan
    return pd.DataFrame([red])


def _broj_u_tekstu(vrednost: float) -> str:
    """Broj za poruku o grešci: hiljade sa tačkom, a manje vrednosti sa decimalnim zarezom."""
    return broj(vrednost, 0) if vrednost >= 1000 else decimalni(vrednost)


def _proveri_opseg(vrednost: float, subjekat: str, jedinica: str, najmanja: float, najveca: float) -> None:
    """
    Javlja grešku kad vrednost izlazi iz opsega koji model poznaje za tu kategoriju:
    dozvoljavam od pola najmanje do 1,5 × najveće vrednosti u bazi.
    """
    if vrednost > 1.5 * najveca:
        granica = f"{_broj_u_tekstu(1.5 * najveca)} {jedinica}".strip()
        raise ValueError(f"{subjekat} može biti najviše {granica} "
                         f"(najveća vrednost u ovoj kategoriji je {_broj_u_tekstu(najveca)}).")
    if vrednost < 0.5 * najmanja:
        granica = f"{_broj_u_tekstu(0.5 * najmanja)} {jedinica}".strip()
        raise ValueError(f"{subjekat} mora biti najmanje {granica} "
                         f"(najmanja vrednost u ovoj kategoriji je {_broj_u_tekstu(najmanja)}).")


# ============================================================================
# Zadatak 5 — klasterovanje (računanje, bez prozora)
# ============================================================================
def klasteruj(s: Stanje, obelezja: list[str], tezine_tekst: list[str], k_tekst: str, kategorija: str) -> dict:
    """
    Proverava izbor, pokreće K-means nad izabranim promenljivim i vraća rečnik sa
    opisom klastera, Silhouette koeficijentom, inercijom i podacima za grafikon.
    """
    # 1) proveravam unos: bar dve promenljive sa spiska, zbir težina veći od 0 i najviše 100%, K od 2 do 12
    if len(obelezja) < 2:
        raise ValueError("Izaberi bar dve ulazne promenljive.")
    if any(o not in kmeans_modul.DOSTUPNA_OBELEZJA for o in obelezja):
        raise ValueError("Izaberi ulazne promenljive sa spiska.")
    tezine = []
    for obelezje, vrednost in zip(obelezja, tezine_tekst):
        vrednost = str(vrednost).strip().replace(",", ".")
        try:
            tezina = float(vrednost) if vrednost else 0.0
        except ValueError:
            raise ValueError(f"Težina za „{kmeans_modul.DOSTUPNA_OBELEZJA[obelezje]}“ mora biti broj od 0 do 100.") from None
        if not np.isfinite(tezina) or tezina < 0:
            raise ValueError(f"Težina za „{kmeans_modul.DOSTUPNA_OBELEZJA[obelezje]}“ mora biti broj od 0 do 100.")
        tezine.append(tezina)
    zbir = sum(tezine)
    if zbir <= 0:
        raise ValueError("Zbir težina mora biti veći od nule.")
    if zbir > 100.0001:
        raise ValueError(f"Zbir težina je {decimalni(zbir)}%, a najviše sme biti 100%.")
    if not str(k_tekst).strip():
        raise ValueError("Upiši broj klastera K (ceo broj između 2 i 12).")
    try:
        k = int(str(k_tekst).strip())
    except ValueError:
        raise ValueError("Broj klastera mora biti ceo broj između 2 i 12.") from None
    if not 2 <= k <= 12:
        raise ValueError("Broj klastera mora biti između 2 i 12.")

    # 2) ako je izabrana kategorija, klasterujem samo nju
    tabela = s.tabela
    if kategorija:
        tabela = tabela[tabela["kategorija"] == kategorija].reset_index(drop=True)

    # 3) kmeans.py izbacuje proizvode bez neke izabrane vrednosti, standardizuje kolone,
    #    svodi težine na zbir 1 i množi kolone korenom težine
    X, zadrzani = kmeans_modul.pripremi_matricu(tabela, obelezja, tezine)
    razlicitih = len(np.unique(X, axis=0))
    if k > razlicitih:
        raise ValueError(f"Traženo je {k} klastera, a proizvoda sa različitim vrednostima ima samo {razlicitih}.")
    ishod = kmeans_modul.kmeans(X, k)
    ocena = kmeans_modul.silhouette(X, ishod["oznake"])
    opis = kmeans_modul.opisi_klastere(zadrzani, ishod["oznake"], obelezja)
    return {
        "klasteri":   opis,
        "silhouette": round(ocena, 3),
        "inercija":   round(ishod["inercija"], 1),
        "iteracija":  ishod["broj_iteracija"],
        "ukupno":     len(zadrzani),
        "obelezja":   obelezja,
        "zadrzani":   zadrzani,
        "oznake":     ishod["oznake"],
    }


def nacrtaj_klastere(figura: Figure, rezultat: dict) -> None:
    """
    Crta u zadatu figuru dijagram rasipanja prve dve izabrane promenljive (obojen po
    klasteru) i stubiće sa brojem proizvoda po klasteru.
    """
    figura.clear()
    leva, desna = figura.subplots(1, 2)
    zadrzani, oznake, obelezja, opis = (rezultat["zadrzani"], rezultat["oznake"],
                                        rezultat["obelezja"], rezultat["klasteri"])
    boje = kmeans_modul.BOJE
    # na levom delu crtam prave vrednosti iz tabele, a ne standardizovane iz matrice X
    prva, druga = obelezja[0], obelezja[1]
    x = pd.to_numeric(zadrzani[prva], errors="coerce")
    y = pd.to_numeric(zadrzani[druga], errors="coerce")
    for broj_klastera in sorted(set(oznake)):
        maska = oznake == broj_klastera
        leva.scatter(x[maska], y[maska], s=14, alpha=0.75, edgecolor="white", linewidth=0.3,
                     color=boje[broj_klastera % len(boje)], label=f"Klaster {broj_klastera}")
    leva.set_xlabel(kmeans_modul.DOSTUPNA_OBELEZJA.get(prva, prva) + (" (RSD)" if prva == "cena_min" else ""))
    leva.set_ylabel(kmeans_modul.DOSTUPNA_OBELEZJA.get(druga, druga) + (" (RSD)" if druga == "cena_min" else ""))
    hiljade = FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", "."))
    leva.xaxis.set_major_formatter(hiljade)
    leva.yaxis.set_major_formatter(hiljade)
    leva.xaxis.set_major_locator(MaxNLocator(nbins=5))
    leva.set_title("Proizvodi po klasterima")
    leva.legend(frameon=False, fontsize=9, markerscale=1.6)
    leva.grid(alpha=0.5)

    # opis mi stiže poređan po prosečnoj ceni, a stubiće ređam po broju klastera
    redosled = opis.sort_values("klaster")
    stubici = desna.bar([f"Klaster {int(k)}" for k in redosled["klaster"]], redosled["broj_proizvoda"],
                        color=[boje[int(k) % len(boje)] for k in redosled["klaster"]],
                        edgecolor="white", linewidth=1.5, width=0.7)
    desna.bar_label(stubici, labels=[broj(v, 0) for v in redosled["broj_proizvoda"]], padding=3, fontsize=9)
    desna.margins(y=0.12)
    desna.set_title("Broj proizvoda po klasteru")
    desna.set_ylabel("Broj proizvoda")
    desna.grid(axis="y", alpha=0.5)
    desna.tick_params(axis="x", labelrotation=20 if len(redosled) <= 6 else 45)
    for strana in (leva, desna):
        strana.spines[["top", "right"]].set_visible(False)
        strana.set_axisbelow(True)
    figura.tight_layout()


# ============================================================================
# Zadatak 6 — preporuke (računanje, bez prozora)
# ============================================================================
def pretrazi(s: Stanje, tekst: str) -> tuple[pd.DataFrame, int]:
    """Vraća prvih 30 proizvoda čiji naziv sadrži sve reči teksta i ukupan broj pogodaka."""
    pogodak = s.preporuke.pretrazi(tekst, len(s.tabela))
    return pogodak.head(30), len(pogodak)


def preporuci(s: Stanje, proizvod_id: int) -> tuple[pd.Series, pd.DataFrame]:
    """Vraća izabrani proizvod i pet njemu najsličnijih iz iste kategorije."""
    red = s.tabela[s.tabela["id"] == proizvod_id]
    if red.empty:
        raise ValueError(f"Ne postoji proizvod sa id={proizvod_id}.")
    return red.iloc[0], s.preporuke.preporuci(proizvod_id, 5)


# ============================================================================
# Prozor
# ============================================================================
class Prozor:
    """
    Glavni prozor sa tri kartice: Predviđanje cene, Klasterovanje i Preporuke.
    Svaka kartica čita unos iz svojih polja, poziva funkcije za računanje iznad
    i prikazuje rezultat ili poruku o grešci.
    """

    def __init__(self, s: Stanje):
        self.s = s
        self.koren = tk.Tk()
        self.koren.title("Analiza tržišta bele tehnike")
        self.koren.geometry("1180x800")
        self.koren.configure(bg=POZADINA)
        self._stil()

        # bordo traka sa naslovom na vrhu prozora
        tk.Label(self.koren, text="Analiza tržišta bele tehnike", bg=BORDO, fg="white",
                 font=("Segoe UI", 15, "bold"), anchor="w", padx=16, pady=10).pack(fill="x")
        self.kartice = ttk.Notebook(self.koren)
        self.kartice.pack(fill="both", expand=True, padx=10, pady=8)
        self._kartica_cena()
        self._kartica_klasteri()
        self._kartica_preporuke()

    def _stil(self) -> None:
        """Podešava izgled: jedna bordo boja za naslove, kartice, zaglavlja tabela i dugmad."""
        stil = ttk.Style(self.koren)
        stil.theme_use("clam")
        stil.configure(".", background=POZADINA, foreground=TEKST, font=("Segoe UI", 10))
        stil.configure("TNotebook", background=POZADINA, borderwidth=0)
        stil.configure("TNotebook.Tab", padding=(14, 6), background=SVETLO)
        stil.map("TNotebook.Tab", background=[("selected", BORDO)], foreground=[("selected", "white")])
        stil.configure("TButton", background=BORDO, foreground="white", padding=(12, 5), borderwidth=0)
        stil.map("TButton", background=[("active", "#5c1730")])
        stil.configure("Treeview", background="white", fieldbackground="white", rowheight=24)
        # izabrani red i izabrani tekst u poljima bojim roze umesto plave boje Windows-a
        stil.map("Treeview", background=[("selected", ROZE)], foreground=[("selected", TEKST)])
        stil.configure("TEntry", selectbackground=ROZE, selectforeground=TEKST)
        stil.configure("TSpinbox", selectbackground=ROZE, selectforeground=TEKST)
        self.koren.option_add("*TCombobox*Listbox.selectBackground", ROZE)
        self.koren.option_add("*TCombobox*Listbox.selectForeground", TEKST)
        stil.configure("Treeview.Heading", background=BORDO, foreground="white", font=("Segoe UI", 10, "bold"))
        stil.map("Treeview.Heading", background=[("active", BORDO)])
        stil.configure("Naslov.TLabel", foreground=BORDO, font=("Segoe UI", 13, "bold"))
        stil.configure("Podnaslov.TLabel", foreground=BORDO, font=("Segoe UI", 10, "bold"))
        stil.configure("Greska.TLabel", foreground=CRVENA, font=("Segoe UI", 10, "bold"))
        stil.configure("Cena.TLabel", foreground=BORDO, font=("Segoe UI", 22, "bold"))
        stil.configure("TCheckbutton", background=POZADINA)
        stil.configure("TCombobox", fieldbackground="white", selectbackground=ROZE, selectforeground=TEKST)

    # ---------- pomoćni delovi prozora ----------
    def _skrol_okvir(self, roditelj) -> ttk.Frame:
        """Pravi okvir sa vertikalnim klizačem i vraća unutrašnji okvir u koji se slažu elementi."""
        platno = tk.Canvas(roditelj, bg=POZADINA, highlightthickness=0)
        klizac = ttk.Scrollbar(roditelj, orient="vertical", command=platno.yview)
        unutra = ttk.Frame(platno, padding=12)
        prozor_id = platno.create_window((0, 0), window=unutra, anchor="nw")
        # unutrašnji okvir prati širinu platna, a platno pamti visinu sadržaja radi klizanja
        unutra.bind("<Configure>", lambda _: platno.configure(scrollregion=platno.bbox("all")))
        platno.bind("<Configure>", lambda d: platno.itemconfigure(prozor_id, width=d.width))
        platno.configure(yscrollcommand=klizac.set)
        platno.bind_all("<MouseWheel>", lambda d: self._tocak(platno, d))
        platno.pack(side="left", fill="both", expand=True)
        klizac.pack(side="right", fill="y")
        return unutra

    @staticmethod
    def _tocak(platno, dogadjaj) -> None:
        """Klizanje točkićem miša; platno se pomera samo kad je miš iznad njega."""
        # ime elementa pod mišem čitam kao tekst: dok je otvorena padajuća lista, Tk vraća njen unutrašnji
        # element koji Python ne poznaje, pa bi winfo_containing pukao; pomeram samo platno pod mišem
        pod_misem = str(platno.tk.call("winfo", "containing", dogadjaj.x_root, dogadjaj.y_root))
        if pod_misem.startswith(str(platno)):
            platno.yview_scroll(int(-dogadjaj.delta / 120), "units")

    @staticmethod
    def _tabela(roditelj, kolone: list[tuple[str, str, int, str]], visina: int) -> ttk.Treeview:
        """Pravi tabelu (Treeview) sa zadatim kolonama: (ključ, naslov, širina, poravnanje)."""
        tabela = ttk.Treeview(roditelj, columns=[k for k, _, _, _ in kolone], show="headings", height=visina)
        for kljuc, naslov, sirina, poravnanje in kolone:
            tabela.heading(kljuc, text=naslov, anchor=poravnanje)
            tabela.column(kljuc, width=sirina, anchor=poravnanje, stretch=True)
        return tabela

    @staticmethod
    def _napuni(tabela: ttk.Treeview, redovi: list[tuple]) -> None:
        """Briše stare redove tabele i upisuje nove."""
        tabela.delete(*tabela.get_children())
        for red in redovi:
            tabela.insert("", "end", values=red)

    # ---------- kartica 1: predviđanje cene ----------
    def _kartica_cena(self) -> None:
        """Forma sa kategorijom, brendom, klasom i tehničkim karakteristikama; ispod je procenjena cena."""
        s = self.s
        spolja = ttk.Frame(self.kartice)
        self.kartice.add(spolja, text="Predviđanje cene")
        okvir = self._skrol_okvir(spolja)
        ttk.Label(okvir, text="Predviđanje cene uređaja", style="Naslov.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        self.poruka_cena = ttk.Label(okvir, text="", style="Greska.TLabel", wraplength=900)
        self.poruka_cena.grid(row=2, column=0, columnspan=4, sticky="w")

        # padajući meniji: kategoriju i klasu prikazujem čitljivim nazivom, a pamtim oznaku iz baze
        self.kategorije_prikaz = {nazivi.kategorija(k): k for k in sorted(s.kategorije, key=nazivi.kategorija)}
        self.klase_prikaz = {o["oznaka"]: o["vrednost"] for o in s.energetske_klase}
        self.unos_cena: dict[str, tk.StringVar] = {}
        ttk.Label(okvir, text="Osnovni podaci", style="Podnaslov.TLabel").grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 2))
        for kolona, (kljuc, naslov, vrednosti) in enumerate([
                ("kategorija", "Kategorija uređaja", [""] + list(self.kategorije_prikaz)),
                ("brend", "Brend", [""] + list(s.brendovi)),
                ("energetska_klasa", "Energetska klasa", ["(nepoznata)"] + list(self.klase_prikaz))]):
            ttk.Label(okvir, text=naslov).grid(row=4, column=kolona, sticky="w", padx=(0, 12))
            promenljiva = tk.StringVar(value="(nepoznata)" if kljuc == "energetska_klasa" else "")
            ttk.Combobox(okvir, textvariable=promenljiva, values=vrednosti, state="readonly", width=30).grid(
                row=5, column=kolona, sticky="w", padx=(0, 12), pady=(0, 6))
            self.unos_cena[kljuc] = promenljiva

        ttk.Label(okvir, text="Tehničke karakteristike", style="Podnaslov.TLabel").grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 2))
        for i, (kljuc, naziv, jedinica) in enumerate(POLJA_FORME):
            red, kolona = 7 + 2 * (i // 4), i % 4
            oznaka = f"{naziv} ({jedinica})" if jedinica else naziv
            ttk.Label(okvir, text=oznaka).grid(row=red, column=kolona, sticky="w", padx=(0, 12))
            promenljiva = tk.StringVar()
            ttk.Entry(okvir, textvariable=promenljiva, width=22).grid(row=red + 1, column=kolona, sticky="w", padx=(0, 12), pady=(0, 6))
            self.unos_cena[kljuc] = promenljiva
        poslednji = 7 + 2 * ((len(POLJA_FORME) - 1) // 4) + 2
        ttk.Button(okvir, text="Izračunaj cenu", command=self.izracunaj_cenu).grid(row=poslednji, column=0, sticky="w", pady=8)

        # rezultat: velika cena i napomena ispod
        self.rezultat_cena = ttk.Label(okvir, text="", style="Cena.TLabel")
        self.rezultat_cena.grid(row=poslednji + 1, column=0, columnspan=4, sticky="w")

        # mere kvaliteta modela na test skupu
        if s.model:
            k = s.model["kvalitet"]
            ttk.Label(okvir, text="Kvalitet modela na test skupu", style="Podnaslov.TLabel").grid(
                row=poslednji + 3, column=0, columnspan=4, sticky="w", pady=(12, 2))
            tabela = self._tabela(okvir, [("m", "Mera", 340, "w"), ("v", "Vrednost", 140, "e")], 6)
            self._napuni(tabela, [
                ("R² u logaritamskom prostoru", broj(k["r2_log_test"], 3)),
                ("R² u dinarima", broj(k["r2_test"], 3)),
                ("RMSE", dinari(k["rmse_test"])),
                ("Srednja apsolutna greška (MAE)", dinari(k["mae_test"])),
                ("Medijana procentualne greške", broj(k["medijana_ape_test"], 1) + "%"),
                ("Srednja procentualna greška (MAPE)", broj(k["mape_test"], 1) + "%"),
            ])
            tabela.grid(row=poslednji + 4, column=0, columnspan=4, sticky="w")

    def izracunaj_cenu(self) -> None:
        """Čita polja forme, računa cenu i ispisuje je ili poruku o grešci."""
        s = self.s
        unos = {k: v.get() for k, v in self.unos_cena.items()}
        unos["kategorija"] = self.kategorije_prikaz.get(unos["kategorija"], unos["kategorija"])
        unos["energetska_klasa"] = self.klase_prikaz.get(unos["energetska_klasa"], "")
        self.poruka_cena.configure(text="")
        try:
            cena = proceni_cenu(unos, s)
        except ValueError as greska:
            self.rezultat_cena.configure(text="")
            self.poruka_cena.configure(text=str(greska))
            return
        except Exception as greska:
            self.rezultat_cena.configure(text="")
            self.poruka_cena.configure(text=f"Greška pri računanju: {greska}")
            return
        self.rezultat_cena.configure(text=f"Procenjena cena: {dinari(cena)}")

    # ---------- kartica 2: klasterovanje ----------
    def _kartica_klasteri(self) -> None:
        """Izbor promenljivih sa težinama, K i kategorije; ispod grafikon i tabele klastera."""
        s = self.s
        spolja = ttk.Frame(self.kartice)
        self.kartice.add(spolja, text="Klasterovanje")
        okvir = self._skrol_okvir(spolja)
        self.okvir_klasteri = okvir
        ttk.Label(okvir, text="Klasterovanje proizvoda (K-srednjih vrednosti)", style="Naslov.TLabel").pack(anchor="w")
        self.poruka_klasteri = ttk.Label(okvir, text="", style="Greska.TLabel", wraplength=900)
        self.poruka_klasteri.pack(anchor="w")

        gore = ttk.Frame(okvir)
        gore.pack(anchor="w", pady=4)
        ttk.Label(gore, text="Broj klastera (K)").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.k_klasteri = tk.StringVar(value="")
        ttk.Spinbox(gore, from_=2, to=12, textvariable=self.k_klasteri, width=6).grid(row=1, column=0, sticky="w", padx=(0, 12))
        ttk.Label(gore, text="Ograniči na kategoriju").grid(row=0, column=1, sticky="w")
        self.kategorija_klasteri = tk.StringVar(value="(sve kategorije)")
        ttk.Combobox(gore, textvariable=self.kategorija_klasteri, state="readonly", width=32,
                     values=["(sve kategorije)"] + [nazivi.kategorija(k) for k in sorted(s.kategorije, key=nazivi.kategorija)]).grid(row=1, column=1, sticky="w")

        ttk.Label(okvir, text="Ulazne promenljive i težine (%)", style="Podnaslov.TLabel").pack(anchor="w", pady=(8, 2))
        self.zbir_tezina = ttk.Label(okvir, text="Zbir težina: 0%")
        self.zbir_tezina.pack(anchor="w")
        mreza = ttk.Frame(okvir)
        mreza.pack(anchor="w", pady=4)
        self.izbor_obelezja: dict[str, tuple[tk.BooleanVar, tk.StringVar]] = {}
        for i, (kljuc, naziv) in enumerate(kmeans_modul.DOSTUPNA_OBELEZJA.items()):
            izabrano, tezina = tk.BooleanVar(value=False), tk.StringVar(value="")
            red, kolona = i // 3, (i % 3) * 2
            ttk.Checkbutton(mreza, text=naziv, variable=izabrano, command=self._osvezi_zbir).grid(
                row=red, column=kolona, sticky="w", padx=(0, 4), pady=2)
            ttk.Entry(mreza, textvariable=tezina, width=6).grid(row=red, column=kolona + 1, sticky="w", padx=(0, 24))
            tezina.trace_add("write", lambda *_: self._osvezi_zbir())
            self.izbor_obelezja[kljuc] = (izabrano, tezina)
        ttk.Button(okvir, text="Pokreni klasterovanje", command=self.pokreni_klasterovanje).pack(anchor="w", pady=8)

        # deo za rezultat popunjavam tek posle računanja
        self.rezultat_klasteri = ttk.Frame(okvir)
        self.rezultat_klasteri.pack(fill="x")
        self.platno_klasteri = None

    def _osvezi_zbir(self) -> None:
        """Sabira težine izabranih promenljivih i ispisuje zbir; preko 100% ga boji crveno."""
        zbir = 0.0
        for izabrano, tezina in self.izbor_obelezja.values():
            if izabrano.get():
                try:
                    zbir += float(tezina.get().replace(",", ".") or 0)
                except ValueError:
                    pass
        self.zbir_tezina.configure(text=f"Zbir težina: {decimalni(zbir)}%",
                                   foreground=CRVENA if zbir > 100.0001 else TEKST)

    def pokreni_klasterovanje(self) -> None:
        """Čita izbor, pokreće klasterovanje i prikazuje brojke, grafikon i tabele."""
        s = self.s
        obelezja = [k for k, (izabrano, _) in self.izbor_obelezja.items() if izabrano.get()]
        tezine = [self.izbor_obelezja[k][1].get() for k in obelezja]
        prikaz = self.kategorija_klasteri.get()
        kategorija = "" if prikaz == "(sve kategorije)" else {nazivi.kategorija(k): k for k in s.kategorije}.get(prikaz, "")
        self.poruka_klasteri.configure(text="")
        for dete in self.rezultat_klasteri.winfo_children():
            dete.destroy()
        try:
            rezultat = klasteruj(s, obelezja, tezine, self.k_klasteri.get(), kategorija)
        except Exception as greska:
            self.poruka_klasteri.configure(text=str(greska))
            return
        okvir = self.rezultat_klasteri
        ttk.Label(okvir, text="Rezultat", style="Podnaslov.TLabel").pack(anchor="w", pady=(6, 2))
        brojke = ttk.Frame(okvir)
        brojke.pack(anchor="w")
        for vrednost, oznaka in [(broj(rezultat["ukupno"], 0), "proizvoda u analizi"),
                                 (broj(rezultat["silhouette"], 3), "Silhouette koeficijent"),
                                 (broj(rezultat["inercija"], 1), "inercija"),
                                 (str(rezultat["iteracija"]), "iteracija do zaustavljanja")]:
            polje = tk.Frame(brojke, bg="white", highlightbackground="#d9c3cb", highlightthickness=1, padx=12, pady=6)
            polje.pack(side="left", padx=(0, 10))
            tk.Label(polje, text=vrednost, bg="white", fg=BORDO, font=("Segoe UI", 16, "bold")).pack(anchor="w")
            tk.Label(polje, text=oznaka, bg="white", fg="#6b5760").pack(anchor="w")

        # grafikon crtam matplotlib-om pravo u prozor
        figura = Figure(figsize=(10, 3.8), dpi=96)
        nacrtaj_klastere(figura, rezultat)
        self.platno_klasteri = FigureCanvasTkAgg(figura, master=okvir)
        self.platno_klasteri.draw()
        self.platno_klasteri.get_tk_widget().pack(fill="x", pady=8)

        # tabela klastera: broj, udeo, prosečna i medijalna cena, opis
        opis = rezultat["klasteri"]
        tabela = self._tabela(okvir, [("k", "Klaster", 90, "w"), ("n", "Proizvoda", 90, "e"), ("u", "Udeo", 70, "e"),
                                      ("p", "Prosečna cena", 120, "e"), ("m", "Medijana cene", 120, "e"),
                                      ("o", "Karakteristike klastera", 560, "w")], len(opis))
        self._napuni(tabela, [(f"Klaster {int(r['klaster'])}", broj(r["broj_proizvoda"], 0), broj(r["udeo_procenat"], 1) + "%",
                               dinari(r["prosecna_cena"]), dinari(r["medijana_cene"]), r["opis"])
                              for _, r in opis.iterrows()])
        tabela.pack(anchor="w", fill="x")

        # prosečne vrednosti izabranih promenljivih po klasteru
        ttk.Label(okvir, text="Prosečne vrednosti izabranih promenljivih po klasteru", style="Podnaslov.TLabel").pack(anchor="w", pady=(10, 2))
        kolone = [("k", "Klaster", 90, "w")] + [(o, kmeans_modul.DOSTUPNA_OBELEZJA[o], 160, "e") for o in rezultat["obelezja"]]
        proseci = self._tabela(okvir, kolone, len(opis))
        redovi = []
        for _, r in opis.iterrows():
            vrednosti = [f"Klaster {int(r['klaster'])}"]
            for o in rezultat["obelezja"]:
                if o == "energetska_rang":
                    vrednosti.append(f"nova: {broj(r.get('prosek_rang_nova'), 1)} · stara: {broj(r.get('prosek_rang_stara'), 1)}")
                else:
                    vrednosti.append(broj(r.get(f"prosek_{o}"), 1))
            redovi.append(tuple(vrednosti))
        self._napuni(proseci, redovi)
        proseci.pack(anchor="w", fill="x")

    # ---------- kartica 3: preporuke ----------
    def _kartica_preporuke(self) -> None:
        """Pretraga po nazivu, spisak pogodaka, izabrani proizvod i pet preporuka."""
        spolja = ttk.Frame(self.kartice)
        self.kartice.add(spolja, text="Preporuke")
        okvir = self._skrol_okvir(spolja)
        ttk.Label(okvir, text="Preporuka sličnih proizvoda", style="Naslov.TLabel").pack(anchor="w")
        self.poruka_preporuke = ttk.Label(okvir, text="", style="Greska.TLabel", wraplength=900)
        self.poruka_preporuke.pack(anchor="w")

        red = ttk.Frame(okvir)
        red.pack(anchor="w", pady=4)
        self.trazeno = tk.StringVar()
        polje = ttk.Entry(red, textvariable=self.trazeno, width=50)
        polje.grid(row=0, column=0, padx=(0, 8))
        polje.bind("<Return>", lambda _: self.pretrazi_proizvode())
        ttk.Button(red, text="Pretraži", command=self.pretrazi_proizvode).grid(row=0, column=1)
        self.broj_pogodaka = ttk.Label(okvir, text="")
        self.broj_pogodaka.pack(anchor="w")

        # tabela pogodaka; dvoklik ili dugme daju preporuke za izabrani red
        self.tabela_pogodaka = self._tabela(okvir, [("id", "Id", 70, "e"), ("naziv", "Naziv", 480, "w"),
                                                    ("brend", "Brend", 130, "w"), ("kategorija", "Kategorija", 200, "w"),
                                                    ("cena", "Cena", 120, "e")], 8)
        self.tabela_pogodaka.pack(anchor="w", fill="x")
        self.tabela_pogodaka.bind("<Double-1>", lambda _: self.preporuke_za_izabrani())
        ttk.Button(okvir, text="Preporuke za izabrani proizvod", command=self.preporuke_za_izabrani).pack(anchor="w", pady=6)

        self.okvir_polazni = ttk.Frame(okvir)
        self.okvir_polazni.pack(anchor="w", fill="x")
        self.tabela_preporuka = self._tabela(okvir, [("r", "#", 40, "e"), ("naziv", "Naziv", 520, "w"),
                                                     ("brend", "Brend", 130, "w"), ("cena", "Cena", 120, "e"),
                                                     ("s", "Sličnost", 100, "e")], 5)

    def pretrazi_proizvode(self) -> None:
        """Traži proizvode po tekstu iz polja i puni tabelu pogodaka."""
        tekst = self.trazeno.get().strip()
        self.poruka_preporuke.configure(text="")
        self._napuni(self.tabela_pogodaka, [])
        if not tekst:
            self.broj_pogodaka.configure(text="")
            return
        pogodak, ukupno = pretrazi(self.s, tekst)
        if pogodak.empty:
            self.broj_pogodaka.configure(text="")
            self.poruka_preporuke.configure(text=f"Nema proizvoda čiji naziv sadrži sve reči iz „{tekst}“.")
            return
        self.broj_pogodaka.configure(text=f"Prikazano je prvih {len(pogodak)} od {ukupno} pogodaka." if ukupno > len(pogodak)
                                     else f"Pogodaka: {ukupno}.")
        self._napuni(self.tabela_pogodaka, [(int(r["id"]), r["naziv"], r["brend"], nazivi.kategorija(r["kategorija"]),
                                             dinari(r["cena_min"])) for _, r in pogodak.iterrows()])

    def preporuke_za_izabrani(self) -> None:
        """Uzima izabrani red iz tabele pogodaka i prikazuje preporuke za taj proizvod."""
        izbor = self.tabela_pogodaka.selection()
        if not izbor:
            self.poruka_preporuke.configure(text="Prvo izaberi proizvod u tabeli.")
            return
        self.prikazi_preporuke(int(self.tabela_pogodaka.item(izbor[0], "values")[0]))

    def prikazi_preporuke(self, proizvod_id: int) -> None:
        """Prikazuje izabrani proizvod i tabelu sa pet preporuka za njega."""
        self.poruka_preporuke.configure(text="")
        for dete in self.okvir_polazni.winfo_children():
            dete.destroy()
        try:
            polazni, preporuke = preporuci(self.s, proizvod_id)
        except Exception as greska:
            self.poruka_preporuke.configure(text=str(greska))
            return
        ttk.Label(self.okvir_polazni, text="Izabrani proizvod", style="Podnaslov.TLabel").pack(anchor="w", pady=(8, 2))
        klasa = polazni.get("energetska_klasa")
        redovi = [("Naziv", polazni["naziv"]), ("Brend", polazni["brend"]),
                  ("Kategorija", nazivi.kategorija(polazni["kategorija"])), ("Cena", dinari(polazni["cena_min"]))]
        if isinstance(klasa, str) and klasa:
            redovi.append(("Energetska klasa", f"{klasa} ({polazni['energetska_skala']} skala)"))
        for naziv, vrednost in redovi:
            r = ttk.Frame(self.okvir_polazni)
            r.pack(anchor="w")
            ttk.Label(r, text=naziv, width=18).pack(side="left")
            ttk.Label(r, text=vrednost, font=("Segoe UI", 10, "bold" if naziv == "Naziv" else "normal")).pack(side="left")
        ttk.Label(self.okvir_polazni, text="Pet najsličnijih proizvoda", style="Podnaslov.TLabel").pack(anchor="w", pady=(10, 2))
        self._napuni(self.tabela_preporuka, [(i + 1, r["naziv"], r["brend"], dinari(r["cena_min"]), broj(r["slicnost"], 4))
                                             for i, (_, r) in enumerate(preporuke.iterrows())])
        self.tabela_preporuka.pack_forget()
        self.tabela_preporuka.pack(anchor="w", fill="x")


def pokreni() -> None:
    """Učitava podatke i modele, pa otvara prozor aplikacije."""
    s = dohvati_stanje()
    prozor = Prozor(s)
    print("[INFO] Prozor aplikacije je otvoren.")
    prozor.koren.mainloop()


if __name__ == "__main__":
    pokreni()
