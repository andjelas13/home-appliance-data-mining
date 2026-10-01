#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
regresija.py — Višestruka linearna regresija sa gradijentnim spustom (Zadatak 4).

Opis:
Skripta učitava prečišćene proizvode, deli ih na trening i test (80/20) i od
njih pravi matricu obeležja. Zatim gradijentnim spustom uči parametre θ kojima
predviđa cenu uređaja. Funkciju troška, gradijent, spust i mere kvaliteta
napisala sam ručno, a numpy koristim samo za rad sa nizovima. Na kraju ispisuje
mere, crta tri grafikona i snima model za aplikaciju.

Model:
    ŷ = θ₀ + θ₁x₁ + θ₂x₂ + ... + θₙxₙ

Funkcija troška (srednja kvadratna greška, uz L2 regularizaciju):
    J(θ) = (1/2m) · Σ(ŷⁱ − yⁱ)²  +  (λ/2m) · Σθⱼ²      (j ≥ 1, θ₀ se ne kažnjava)

Korak gradijentnog spusta:
    θ := θ − (α/m) · [ Xᵀ(Xθ − y) + λ·θ' ]              (θ'₀ = 0)

Zašto logaritam cene (podrazumevano; --bez_log_cene to isključuje):
Cene idu od nekoliko stotina do preko tri miliona dinara, pa bi na sirovoj ceni
najskuplji uređaji nosili najveće kvadrate greške. Sa log(cena) model uči odnose
umesto razlika: promašaj od 5.000 din na uređaju od 20.000 vredi isto kao
promašaj od 50.000 din na uređaju od 200.000. Predikciju vraćam u dinare preko
exp(), a R² navodim i u log prostoru i u dinarima.

Ulazi:
    šema preciscena (preko modula podaci.py)

Izlazi:
    izvestaj/modeli/regresija_model.json      — naučeni parametri (za aplikaciju)
    izvestaj/grafikoni/07_kriva_ucenja.png    — kriva učenja
    izvestaj/grafikoni/08_predvidjeno_stvarno.png — stvarna naspram predviđene cene (test skup)
    izvestaj/grafikoni/09_uticaj_obelezja.png  — najveći koeficijenti modela
    izvestaj/modeli/regresija_eksperimenti.csv — poređenje podešavanja (samo uz --eksperimenti)
    izvestaj/grafikoni/07b_kriva_ucenja_stope.png — trošak za više stopa učenja (samo uz --eksperimenti)

Svako pokretanje bez --eksperimenti prepisuje snimljeni model i grafikone 07, 08 i 09,
i to sa bilo kojom opcijom: posle „--kategorija televizor“ aplikacija radi sa modelom
naučenim samo na televizorima, pa model iz izveštaja treba obnoviti pokretanjem bez
opcija. Uz --eksperimenti se model ne snima, nego se prepisuju 07b i eksperimenti u CSV-u.

Primer poziva:
    python regresija.py                              (model iz izveštaja; tako ga zove i pokreni.bat)
    python regresija.py --stopa_ucenja 0.05 --iteracije 10000
    python regresija.py --kategorija televizor --udeo_testa 0.3
    python regresija.py --bez_log_cene --regularizacija 1.0
    python regresija.py --eksperimenti
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import matplotlib
# biram Agg, jer mi grafikone crta pravo u fajl, bez otvaranja prozora
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

# u putanju dodajem folder models, da uvezem podaci.py, i folder kod, zbog paketa zajednicko
sys.path.append(str(Path(__file__).resolve().parent))
from podaci import Priprema, ucitaj_preciscene, podeli
sys.path.append(str(Path(__file__).resolve().parents[1]))
from zajednicko.putanje import FOLDER_MODELA, FOLDER_GRAFIKONA
from zajednicko.nazivi import obelezje_modela

# boje grafikona su iste kao u grafikoni.py: bordo je osnovna, a oker mi služi za naglasak
BORDO, TAMNI_BORDO, OKER = "#7A1F3D", "#4E1226", "#C47A93"
POZADINA, TEKST, PRIGUSENO = "#FBF4F6", "#2B2024", "#6B4F59"
IVICA, MREZA = "#8C6A76", "#C9A3B0"
# za četiri stope učenja uzimam četiri jasno različita tona: bordo, oker, škriljac i maslinastu
BOJE_STOPA = ["#4E1226", "#B23A5B", "#8C8C8C", "#D98BA0"]

# svim grafikonima sam zadala isti font, veličine slova i boje, kao u pisanom radu
plt.rcParams.update({
    "font.family": "Times New Roman",
    "axes.titlesize": 15, "axes.titleweight": "bold", "axes.titlecolor": TAMNI_BORDO,
    "axes.titlepad": 10, "axes.labelsize": 13, "axes.labelcolor": TEKST,
    "axes.edgecolor": IVICA, "axes.facecolor": POZADINA, "figure.facecolor": POZADINA,
    "text.color": TEKST, "xtick.color": IVICA, "ytick.color": IVICA,
    "xtick.labelcolor": TEKST, "ytick.labelcolor": TEKST,
    "grid.color": MREZA, "legend.edgecolor": MREZA,
    "xtick.labelsize": 12, "ytick.labelsize": 12, "legend.fontsize": 12,
    "figure.dpi": 120, "savefig.bbox": "tight",
})


# ============================================================================
# 1. OSNOVNE FUNKCIJE MODELA — sve ručno napisane
# ============================================================================
def dodaj_slobodni_clan(X: np.ndarray) -> np.ndarray:
    """
    Funkcija dodaje kolonu jedinica na početak matrice X i vraća novu matricu.
    Ta kolona se množi sa θ₀, pa slobodni član učim isto kao ostale parametre.
    """
    # np.ones pravi kolonu jedinica visine X.shape[0], a hstack je stavlja levo od svih obeležja, kao kolonu 0
    return np.hstack([np.ones((X.shape[0], 1)), X])


def predvidi(X: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """
    Računa predikciju ŷ = X · θ za sve redove odjednom i vraća vektor.
    X već ima kolonu jedinica, pa je θ₀ uključen u proizvod.
    """
    # ovo mi je ista prava kao x * coef_ + intercept_ sa vežbi, samo za sva obeležja
    # odjednom: θ₀ je intercept_, a ostale θ su coef_
    return X @ theta


def funkcija_troska(X: np.ndarray, y: np.ndarray, theta: np.ndarray,
                    lambda_reg: float = 0.0) -> float:
    """
    Računa srednju kvadratnu grešku podeljenu sa 2, uz L2 kaznu, i vraća broj.

        J(θ) = (1/2m) · Σ(ŷ − y)²  +  (λ/2m) · Σθⱼ²    za j ≥ 1

    Dvojku u imeniocu stavila sam zbog izvoda: kvadrat daje množilac 2, pa se
    skrate. θ₀ se ne kažnjava, jer samo pomera nivo predikcije.
    """
    # broj_uzoraka je m iz formule, tj. broj redova u X
    broj_uzoraka = X.shape[0]
    # greska mi je vektor (ŷ − y), a greska @ greska daje zbir kvadrata grešaka
    greska = predvidi(X, theta) - y
    trosak = (greska @ greska) / (2 * broj_uzoraka)

    # L2 kaznu dodajem samo kad je λ > 0 i sabiram kvadrate theta[1:], znači bez θ₀
    if lambda_reg > 0:
        kazna = lambda_reg * (theta[1:] @ theta[1:]) / (2 * broj_uzoraka)
        trosak += kazna
    return float(trosak)


def gradijent(X: np.ndarray, y: np.ndarray, theta: np.ndarray,
              lambda_reg: float = 0.0) -> np.ndarray:
    """
    Računa gradijent funkcije troška po svim parametrima i vraća vektor dužine θ:

        ∂J/∂θ = (1/m) · Xᵀ(Xθ − y)  +  (λ/m) · θ'      (θ'₀ = 0)

    Za kolonu j, (Xᵀ(Xθ − y))ⱼ je zbir grešaka pomnoženih vrednostima te kolone,
    tj. koliko baš to obeležje doprinosi ukupnoj grešci.
    """
    broj_uzoraka = X.shape[0]
    # isti vektor greške kao u funkciji troška; X.T @ greska ga raspoređuje po kolonama,
    # pa za svako obeležje dobijam njegov deo izvoda
    greska = predvidi(X, theta) - y
    izvod = (X.T @ greska) / broj_uzoraka

    # množenjem dobijam novi niz, pa kazna[0] = 0 ne menja samu thetu, a θ₀ ostaje
    # bez kazne kao i u funkciji troška
    if lambda_reg > 0:
        kazna = (lambda_reg / broj_uzoraka) * theta
        kazna[0] = 0.0                     # slobodni član ne regularizujem
        izvod = izvod + kazna
    return izvod


def gradijentni_spust(X: np.ndarray, y: np.ndarray, stopa_ucenja: float,
                      broj_iteracija: int, lambda_reg: float = 0.0,
                      prag_zaustavljanja: float = 1e-10,
                      ispisuj: bool = True) -> tuple[np.ndarray, list[float]]:
    """
    Funkcija obučava model gradijentnim spustom i vraća naučene θ i istoriju
    troška (za krivu učenja). Kreće od θ = 0 i u svakoj iteraciji pravi korak
    suprotan gradijentu, dužine srazmerne stopi učenja α:

        θ := θ − α · ∂J/∂θ

    Staje posle broj_iteracija, ili pre toga kad se trošak promeni za manje od
    prag_zaustavljanja ili kad trošak više nije konačan broj.
    """
    # krećem od θ = 0, a u listu istorija upisujem trošak posle svake iteracije, za krivu učenja
    theta = np.zeros(X.shape[1])
    istorija = []
    prethodni_trosak = None

    # u svakoj iteraciji prvo pravim korak spusta, pa računam novi trošak, pa proveravam da li da stanem
    for iteracija in range(1, broj_iteracija + 1):
        theta = theta - stopa_ucenja * gradijent(X, y, theta, lambda_reg)
        trosak = funkcija_troska(X, y, theta, lambda_reg)
        istorija.append(trosak)

        # ako trošak postane beskonačan ili NaN, α mi je prevelika i spust divergira, pa prekidam
        if not np.isfinite(trosak):
            print(f"[GRESKA] Trošak je divergirao u iteraciji {iteracija}. "
                  f"Smanji stopu učenja (sada je {stopa_ucenja}).")
            break

        # rani prekid sam stavila za slučaj kad se trošak između dve iteracije skoro ne menja
        if prethodni_trosak is not None and abs(prethodni_trosak - trosak) < prag_zaustavljanja:
            if ispisuj:
                print(f"[INFO] Zaustavljeno u iteraciji {iteracija:,} "
                      f"(promena troška manja od {prag_zaustavljanja})")
            break
        prethodni_trosak = trosak

        # trošak ispisujem na svakih 10% od zadatog broja iteracija, da pratim kako opada
        if ispisuj and (iteracija % max(1, broj_iteracija // 10) == 0):
            print(f"[INFO] iteracija {iteracija:>6,}   trošak = {trosak:.6f}")

    return theta, istorija


# ============================================================================
# 2. MERE KVALITETA — takođe ručno
# ============================================================================
def r2_skor(stvarno: np.ndarray, predvidjeno: np.ndarray) -> float:
    """
    Računa koeficijent determinacije i vraća ga kao broj:
        R² = 1 − Σ(y − ŷ)² / Σ(y − ȳ)²

    Pokazuje koliki deo raspršenosti y model objašnjava. R² = 1 je savršeno,
    R² = 0 znači da model nije bolji od predviđanja proseka, a ispod 0 je gori.
    """
    # ovo je isti R² koji na vežbama vraća model.score(x_test, y_test), samo ga ovde računam ručno.
    # ostatak mi je zbir kvadrata grešaka, a ukupno zbir kvadrata odstupanja od proseka;
    # ako su sve stvarne vrednosti iste, ukupno je 0, pa vraćam 0 da ne delim nulom
    ostatak = ((stvarno - predvidjeno) ** 2).sum()
    ukupno = ((stvarno - stvarno.mean()) ** 2).sum()
    return float(1 - ostatak / ukupno) if ukupno else 0.0


def rmse(stvarno: np.ndarray, predvidjeno: np.ndarray) -> float:
    """
    Računa koren srednje kvadratne greške, u istoj jedinici kao cena (dinari).
    Greške se kvadriraju, pa veliki promašaji utiču više nego kod MAE.
    """
    # prvo kvadriram razlike, pa uzimam prosek, pa koren, da se vratim u dinare
    return float(np.sqrt(((stvarno - predvidjeno) ** 2).mean()))


def mae(stvarno: np.ndarray, predvidjeno: np.ndarray) -> float:
    """Računa srednju apsolutnu grešku, tj. za koliko dinara model u proseku promaši cenu."""
    # ovde uzimam apsolutnu vrednost umesto kvadrata, pa svaki dinar promašaja vredi isto
    return float(np.abs(stvarno - predvidjeno).mean())


def mape(stvarno: np.ndarray, predvidjeno: np.ndarray) -> float:
    """
    Računa srednju apsolutnu procentualnu grešku: prosek |y − ŷ| / y, puta 100.
    Za cene je razumljivija od RMSE, jer kaže za koliko posto model u proseku promaši.
    """
    # delim sa stvarno, jer procenat greške merim u odnosu na pravu cenu
    return float((np.abs(stvarno - predvidjeno) / stvarno).mean() * 100)


def medijana_ape(stvarno: np.ndarray, predvidjeno: np.ndarray) -> float:
    """
    Računa medijanu apsolutne procentualne greške, u procentima.
    Navodim je uz MAPE, jer nekoliko jako promašenih uređaja podiže prosek,
    a medijana pokazuje grešku na tipičnom proizvodu.
    """
    # isti količnik kao u mape(), samo umesto proseka uzimam np.median
    return float(np.median(np.abs(stvarno - predvidjeno) / stvarno) * 100)


# ============================================================================
# 3. OBUČAVANJE I OCENA
# ============================================================================
def obuci(tabela: pd.DataFrame, stopa_ucenja: float, broj_iteracija: int,
          lambda_reg: float, log_cena: bool, udeo_testa: float,
          ispisuj: bool = True, interakcije: bool = True) -> dict:
    """
    Funkcija deli tabelu na trening i test, uči pripremu obeležja samo na
    treningu i obučava model gradijentnim spustom. Vraća rečnik sa θ, istorijom
    troška, pripremom i merama kvaliteta na trening i test skupu.
    """
    # 1) redove nasumično delim na trening i test preko podeli() (podrazumevano 80/20);
    #    na vežbama je to radio train_test_split sa test_size=0.25
    indeksi_trening, indeksi_test = podeli(len(tabela), udeo_testa)
    trening = tabela.iloc[indeksi_trening].reset_index(drop=True)
    test = tabela.iloc[indeksi_test].reset_index(drop=True)

    # 2) medijane, one-hot vrednosti i standardizaciju učim samo na treningu,
    #    a na test ih samo primenjujem, da mi podaci iz testa ne procure u učenje
    priprema = Priprema(interakcije=interakcije)
    X_trening, nazivi = priprema.nauci_i_primeni(trening)
    X_test = priprema.primeni(test)

    # 3) i trening i test dobijaju kolonu jedinica za slobodni član θ₀
    X_trening = dodaj_slobodni_clan(X_trening)
    X_test = dodaj_slobodni_clan(X_test)

    # cene izvlačim kao float nizove; one ostaju u dinarima i nad njima računam mere
    cena_trening = trening["cena_min"].to_numpy(dtype=float)
    cena_test = test["cena_min"].to_numpy(dtype=float)

    # 4) model mi uči logaritam cene, osim ako je zadato --bez_log_cene
    y_trening = np.log(cena_trening) if log_cena else cena_trening

    # merim koliko traje sam gradijentni spust, bez pripreme podataka
    pocetak = time.perf_counter()
    theta, istorija = gradijentni_spust(X_trening, y_trening, stopa_ucenja,
                                        broj_iteracija, lambda_reg, ispisuj=ispisuj)
    trajanje = time.perf_counter() - pocetak

    # 5) ako sam učila log cene, predikcije vraćam u dinare preko exp(), da RMSE i MAE budu u dinarima
    predikcija_trening = predvidi(X_trening, theta)
    predikcija_test = predvidi(X_test, theta)
    if log_cena:
        predikcija_trening = np.exp(predikcija_trening)
        predikcija_test = np.exp(predikcija_test)

    # R² računam u oba prostora. U log prostoru mi pokazuje koliko je model naučio,
    # a u dinarima je niži jer model greši relativno (za procenat cene), pa su greške
    # u dinarima najveće kod skupih uređaja i one preovlađuju u zbiru kvadrata.
    # Logaritam predikcije postoji samo za pozitivnu cenu; model nad sirovom cenom
    # (--bez_log_cene) može da predvidi i negativnu, pa tada R² u log prostoru postavljam na None.
    if (predikcija_trening > 0).all() and (predikcija_test > 0).all():
        r2_log_trening = r2_skor(np.log(cena_trening), np.log(predikcija_trening))
        r2_log_test = r2_skor(np.log(cena_test), np.log(predikcija_test))
    else:
        r2_log_trening = r2_log_test = None

    # sve što mi treba za ispis, grafikone, snimanje i eksperimente vraćam u jednom rečniku
    return {
        "theta":            theta,
        "istorija":         istorija,
        "priprema":         priprema,
        "nazivi":           nazivi,
        "trajanje_s":       trajanje,
        "broj_iteracija":   len(istorija),
        "stopa_ucenja":     stopa_ucenja,
        "lambda_reg":       lambda_reg,
        "log_cena":         log_cena,
        "n_trening":        len(trening),
        "n_test":           len(test),
        "r2_trening":       r2_skor(cena_trening, predikcija_trening),
        "r2_test":          r2_skor(cena_test, predikcija_test),
        "r2_log_trening":   r2_log_trening,
        "r2_log_test":      r2_log_test,
        "medijana_ape_test": medijana_ape(cena_test, predikcija_test),
        "rmse_trening":     rmse(cena_trening, predikcija_trening),
        "rmse_test":        rmse(cena_test, predikcija_test),
        "mae_test":         mae(cena_test, predikcija_test),
        "mape_test":        mape(cena_test, predikcija_test),
        "cena_test":        cena_test,
        "predikcija_test":  predikcija_test,
    }


def r2_log_tekst(vrednost: float | None) -> str:
    """Vraća R² u log prostoru sa četiri decimale, ili „nedefinisano“ kad ga nema."""
    # None dobijam kad je neka predikcija bila ≤ 0, pa tada umesto broja pišem reč
    return "nedefinisano" if vrednost is None else f"{vrednost:.4f}"


def ispisi_rezultat(rezultat: dict) -> None:
    """Ispisuje tabelu mera za trening i test skup; MAE i obe MAPE postoje samo za test."""
    # mere poravnavam na širinu 22 i 14 znakova, da trening i test stoje u urednim kolonama
    print(f"\n[OK] Model obučen za {rezultat['trajanje_s']:.1f} s "
          f"({rezultat['broj_iteracija']:,} iteracija)")
    print(f"       {'mera':22} {'trening':>14} {'test':>14}")
    print(f"       {'R² (u dinarima)':22} {rezultat['r2_trening']:>14.4f} {rezultat['r2_test']:>14.4f}")
    print(f"       {'R² (log prostor)':22} {r2_log_tekst(rezultat['r2_log_trening']):>14} "
          f"{r2_log_tekst(rezultat['r2_log_test']):>14}")
    print(f"       {'RMSE (RSD)':22} {rezultat['rmse_trening']:>14,.0f} {rezultat['rmse_test']:>14,.0f}")
    # MAE i obe MAPE računam samo na testu, pa kolonu za trening ostavljam praznu
    print(f"       {'MAE (RSD)':22} {'':>14} {rezultat['mae_test']:>14,.0f}")
    print(f"       {'MAPE srednja (%)':22} {'':>14} {rezultat['mape_test']:>14.1f}")
    print(f"       {'MAPE medijana (%)':22} {'':>14} {rezultat['medijana_ape_test']:>14.1f}")


# ============================================================================
# 4. GRAFIKONI
# ============================================================================
def decimalni(vrednost: float, decimala: int | None = None) -> str:
    """Pretvara broj u tekst sa decimalnim zarezom (0,1 umesto 0.1), za natpise na grafikonima."""
    # bez zadatih decimala koristim :g, koji ne dopisuje nule, pa 0.1 ostaje 0,1, a ne 0,100000
    tekst = f"{vrednost:.{decimala}f}" if decimala is not None else f"{vrednost:g}"
    return tekst.replace(".", ",")


def nacrtaj_krivu_ucenja(rezultat: dict) -> None:
    """Crta vrednost funkcije troška kroz iteracije i snima 07_kriva_ucenja.png."""
    # pravim folder za grafikone ako ne postoji, pa crtam trošak redom za svaku iteraciju
    FOLDER_GRAFIKONA.mkdir(parents=True, exist_ok=True)
    figura, osa = plt.subplots(figsize=(10, 6))
    osa.plot(range(1, len(rezultat["istorija"]) + 1), rezultat["istorija"], color=BORDO, linewidth=2)
    osa.set_title("Kriva učenja — vrednost funkcije troška kroz iteracije")
    osa.set_xlabel("Iteracija gradijentnog spusta")
    osa.set_ylabel("J(θ)")
    # y osu sam stavila na logaritamsku, da se pored brzog pada na početku vidi i spori pad kasnije;
    # na x osi hiljade odvajam tačkom
    osa.set_yscale("log")
    osa.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", ".")))
    osa.grid(alpha=0.3)
    osa.spines[["top", "right"]].set_visible(False)
    # broj iteracija i α, λ formatiram odvojeno: kod iteracija zarez za hiljade
    # menjam tačkom, a decimalni() kod α i λ menja tačku zarezom
    iteracija = f"{rezultat['broj_iteracija']:,}".replace(",", ".")
    figura.text(0.99, 0.01,
                f"α = {decimalni(rezultat['stopa_ucenja'])}; λ = {decimalni(rezultat['lambda_reg'])}; "
                f"{iteracija} iteracija",
                ha="right", fontsize=11, color=PRIGUSENO)
    # sliku snimam i zatvaram figuru, da mi ne ostaje otvorena u memoriji
    figura.savefig(FOLDER_GRAFIKONA / "07_kriva_ucenja.png")
    plt.close(figura)
    print("[OK] 07_kriva_ucenja.png")


def nacrtaj_krive_za_stope(krive: dict) -> None:
    """
    Crta J(θ) kroz iteracije za svaku stopu učenja iz eksperimenata, na istom grafikonu,
    i snima 07b_kriva_ucenja_stope.png.
    """
    # granice y ose uzimam iz stopa koje ne divergiraju, da rast divergentne ne sabije ostale
    # krive; kad bi sve divergirale, granice ne bih imala odakle da uzmem, pa grafikon ne crtam
    konacne = [istorija for istorija in krive.values() if np.isfinite(istorija[-1])]
    if not konacne:
        print("[UPOZORENJE] Sve stope učenja divergiraju, pa 07b_kriva_ucenja_stope.png ne crtam.")
        return
    najmanji, najveci = min(min(i) for i in konacne), max(max(i) for i in konacne)
    FOLDER_GRAFIKONA.mkdir(parents=True, exist_ok=True)
    figura, osa = plt.subplots(figsize=(10, 6))
    for boja, (stopa, istorija) in zip(BOJE_STOPA, krive.items()):
        oznaka = f"α = {decimalni(stopa)}"
        # trošak stope koja divergira raste do beskonačnosti, pa ga crtam kao liniju pri vrhu ose,
        # do iteracije u kojoj je spust prekinut
        if not np.isfinite(istorija[-1]):
            istorija = np.minimum(istorija, najveci * 1.5)
            oznaka += " (divergira)"
        osa.plot(range(1, len(istorija) + 1), istorija, color=boja, linewidth=2, label=oznaka)
    osa.set_yscale("log")
    osa.set_ylim(najmanji / 2, najveci * 2)
    osa.set_title("Kriva učenja za različite stope učenja α")
    osa.set_xlabel("Iteracija gradijentnog spusta")
    osa.set_ylabel("J(θ)")
    osa.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", ".")))
    osa.legend()
    osa.grid(alpha=0.3)
    osa.spines[["top", "right"]].set_visible(False)
    figura.savefig(FOLDER_GRAFIKONA / "07b_kriva_ucenja_stope.png")
    plt.close(figura)
    print("[OK] 07b_kriva_ucenja_stope.png")


def nacrtaj_predvidjeno_stvarno(rezultat: dict) -> None:
    """Crta stvarnu naspram predviđene cene na test skupu i snima 08_predvidjeno_stvarno.png."""
    figura, osa = plt.subplots(figsize=(8, 8))
    stvarno, predvidjeno = rezultat["cena_test"], rezultat["predikcija_test"]
    # svaka tačka mi je jedan proizvod iz test skupa; alpha je mala jer se tačke dosta preklapaju
    osa.scatter(stvarno, predvidjeno, s=12, alpha=0.35, color=BORDO, edgecolor="none")

    # isprekidanu dijagonalu y = x crtam oker bojom, da se jasno vidi preko bordo tačaka, kao
    # liniju tačnih pogodaka; obe ose sam stavila na logaritamske, jer cene idu od stotina do
    # miliona dinara
    granica = max(stvarno.max(), predvidjeno.max())
    osa.plot([0, granica], [0, granica], "--", color=OKER, linewidth=2.2,
             label="savršena predikcija")
    osa.set_xscale("log")
    osa.set_yscale("log")
    osa.set_title("Predviđena u odnosu na stvarnu cenu (test skup)")
    osa.set_xlabel("Stvarna cena (RSD)")
    osa.set_ylabel("Predviđena cena (RSD)")
    osa.legend()
    osa.grid(alpha=0.25)
    # dole desno ispisujem R² u oba prostora i medijanu greške, sa decimalnim zarezom
    figura.text(0.99, 0.01,
                f"R² (log) = {decimalni(rezultat['r2_log_test'], 3) if rezultat['r2_log_test'] is not None else 'nedefinisano'}   "
                f"R² (RSD) = {decimalni(rezultat['r2_test'], 3)}   "
                f"medijana greške = {decimalni(rezultat['medijana_ape_test'], 1)}%",
                ha="right", fontsize=11, color=PRIGUSENO)
    figura.savefig(FOLDER_GRAFIKONA / "08_predvidjeno_stvarno.png")
    plt.close(figura)
    print("[OK] 08_predvidjeno_stvarno.png")


def nacrtaj_najuticajnija(rezultat: dict, koliko: int = 15) -> None:
    """
    Crta obeležja sa najvećim |θ| (bez θ₀) i snima 09_uticaj_obelezja.png.
    Bordo traka je obeležje koje podiže cenu, oker ono koje je spušta.
    """
    # theta[1:] mi preskače θ₀, pa se koeficijenti poklapaju sa nazivima kolona;
    # sortiram po apsolutnoj vrednosti, a iloc[::-1] okreće redosled, da najveći bude na vrhu
    theta, nazivi = rezultat["theta"], rezultat["nazivi"]
    tezine = pd.Series(theta[1:], index=nazivi).sort_values(key=abs, ascending=False)
    izbor = tezine.head(koliko).iloc[::-1]

    figura, osa = plt.subplots(figsize=(10, 7))
    # pozitivan koeficijent bojim bordo, a negativan oker bojom; nazive kolona prevodim preko obelezje_modela
    boje = [BORDO if v > 0 else OKER for v in izbor]
    osa.barh([obelezje_modela(n) for n in izbor.index], izbor.values, color=boje)
    osa.set_title(f"Najveći koeficijenti modela (prvih {koliko} po apsolutnoj vrednosti)")
    osa.set_xlabel("Koeficijent θ (na standardizovanim obeležjima)")
    # na x osi pišem decimalni zarez i pravi znak minus umesto crtice
    osa.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}".replace(".", ",").replace("-", "−")))
    osa.axvline(0, color=TAMNI_BORDO, linewidth=0.8)
    osa.spines[["top", "right"]].set_visible(False)
    figura.savefig(FOLDER_GRAFIKONA / "09_uticaj_obelezja.png")
    plt.close(figura)
    print("[OK] 09_uticaj_obelezja.png")


# ============================================================================
# 5. SNIMANJE MODELA
# ============================================================================
def snimi_model(rezultat: dict) -> None:
    """
    Snima θ, nazive kolona, naučenu pripremu, mere i podešavanja u
    regresija_model.json, da aplikacija ne mora ponovo da obučava model.
    """
    # thetu iz numpy niza pretvaram u listu, a pripremu u rečnik, jer JSON ne zna za numpy
    FOLDER_MODELA.mkdir(parents=True, exist_ok=True)
    zapis = {
        "theta":        rezultat["theta"].tolist(),
        "nazivi":       rezultat["nazivi"],
        "log_cena":     rezultat["log_cena"],
        "priprema":     rezultat["priprema"].kao_recnik(),
        "kvalitet": {
            # čuvam i mere na treningu, da se u izveštaju vidi razlika
            # trening–test, tj. da li ima preprilagođavanja
            "r2_trening":     rezultat["r2_trening"],
            "r2_log_trening": rezultat["r2_log_trening"],
            "rmse_trening":   rezultat["rmse_trening"],
            "r2_test":     rezultat["r2_test"],
            "r2_log_test": rezultat["r2_log_test"],
            "rmse_test": rezultat["rmse_test"],
            "mae_test":  rezultat["mae_test"],
            "mape_test": rezultat["mape_test"],
            "medijana_ape_test": rezultat["medijana_ape_test"],
            "n_trening": rezultat["n_trening"],
            "n_test":    rezultat["n_test"],
        },
        "podesavanja": {
            "stopa_ucenja":   rezultat["stopa_ucenja"],
            "lambda_reg":     rezultat["lambda_reg"],
            "broj_iteracija": rezultat["broj_iteracija"],
            "n_trening":      rezultat["n_trening"],
            "n_test":         rezultat["n_test"],
        },
    }
    # ensure_ascii=False mi ostavlja naša slova u JSON-u čitljiva
    putanja = FOLDER_MODELA / "regresija_model.json"
    putanja.write_text(json.dumps(zapis, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Model snimljen: {putanja}")


# ============================================================================
# 6. EKSPERIMENTI
# ============================================================================
def zaokruzi(vrednost: float, decimala: int, oznaka: str = "nedefinisano"):
    """
    Zaokružuje meru za tabelu eksperimenata; ako mera nije konačan broj, vraća
    prosleđenu oznaku („divergiralo" ili „nedefinisano"). Nedefinisano je npr.
    R² u log prostoru kad model bez log cene predvidi negativnu cenu, jer
    logaritam negativnog broja ne postoji.
    """
    # None, inf ili NaN menjam oznakom; za 0 decimala upisujem ceo broj (RMSE, MAE)
    if vrednost is None or not np.isfinite(vrednost):
        return oznaka
    return round(float(vrednost), decimala) if decimala else int(round(float(vrednost)))


def pokreni_eksperimente(tabela: pd.DataFrame, udeo_testa: float) -> None:
    """
    Obučava model sa više podešavanja (α, broj iteracija, λ, log cene,
    interakcije), ispisuje poređenje i snima ga u regresija_eksperimenti.csv.
    """
    # redom sam stavila: četiri stope učenja, jedno sa više iteracija, dve vrednosti λ i sirovu cenu
    podesavanja = [
        {"stopa_ucenja": 0.001, "broj_iteracija": 3000,  "lambda_reg": 0.0, "log_cena": True},
        {"stopa_ucenja": 0.01,  "broj_iteracija": 3000,  "lambda_reg": 0.0, "log_cena": True},
        {"stopa_ucenja": 0.1,   "broj_iteracija": 3000,  "lambda_reg": 0.0, "log_cena": True},
        {"stopa_ucenja": 0.3,   "broj_iteracija": 3000,  "lambda_reg": 0.0, "log_cena": True},
        {"stopa_ucenja": 0.1,   "broj_iteracija": 10000, "lambda_reg": 0.0, "log_cena": True},
        {"stopa_ucenja": 0.1,   "broj_iteracija": 3000,  "lambda_reg": 1.0, "log_cena": True},
        {"stopa_ucenja": 0.1,   "broj_iteracija": 3000,  "lambda_reg": 10.0, "log_cena": True},
        {"stopa_ucenja": 0.1,   "broj_iteracija": 3000,  "lambda_reg": 0.0, "log_cena": False},
        # poslednje je bez članova interakcije: jedan koeficijent po karakteristici za sve
        # kategorije, da vidim koliko mi interakcije doprinose modelu
        {"stopa_ucenja": 0.1,   "broj_iteracija": 3000,  "lambda_reg": 0.0, "log_cena": True,
         "interakcije": False},
    ]

    # svako podešavanje obučavam na istoj podeli (seme u podeli() je fiksno) i bez ispisa iteracija;
    # istoriju troška prva četiri (različite stope učenja) pamtim za zajednički grafikon
    redovi, krive = [], {}
    for redni_broj, podesavanje in enumerate(podesavanja, start=1):
        print(f"\n[INFO] Eksperiment {redni_broj}/{len(podesavanja)}: {podesavanje}")
        rezultat = obuci(tabela, udeo_testa=udeo_testa, ispisuj=False, **podesavanje)
        if redni_broj <= 4:
            krive[podesavanje["stopa_ucenja"]] = rezultat["istorija"]
        # divergenciju gledam po poslednjem trošku, a ne po merama, jer mera može
        # biti nedefinisana i kad je spust konvergirao
        divergiralo = not np.isfinite(rezultat["istorija"][-1])
        oznaka = "divergiralo" if divergiralo else "nedefinisano"
        # prvo upisujem interakcije=True, a podešavanje koje ih isključuje to pregazi
        redovi.append({
            **{"interakcije": True, **podesavanje},
            "izvrseno_iteracija": rezultat["broj_iteracija"],
            "divergiralo":    divergiralo,
            "negativnih_predikcija": int((rezultat["predikcija_test"] <= 0).sum()) if not divergiralo else None,
            "r2_trening":     zaokruzi(rezultat["r2_trening"], 4, oznaka),
            "r2_test":        zaokruzi(rezultat["r2_test"], 4, oznaka),
            "r2_log_test":    zaokruzi(rezultat["r2_log_test"], 4, oznaka),
            "medijana_ape":   zaokruzi(rezultat["medijana_ape_test"], 1, oznaka),
            "rmse_test":   zaokruzi(rezultat["rmse_test"], 0, oznaka),
            "mae_test":    zaokruzi(rezultat["mae_test"], 0, oznaka),
            "mape_test":   zaokruzi(rezultat["mape_test"], 1, oznaka),
            "trajanje_s":  round(rezultat["trajanje_s"], 1),
        })
        print(f"       R² test = {rezultat['r2_test']:.4f}   MAPE = {rezultat['mape_test']:.1f}%")

    # celu tabelu poređenja snimam u CSV i ispisujem je u konzolu
    FOLDER_MODELA.mkdir(parents=True, exist_ok=True)
    putanja = FOLDER_MODELA / "regresija_eksperimenti.csv"
    pd.DataFrame(redovi).to_csv(putanja, index=False, encoding="utf-8")
    print(f"\n[OK] Poređenje eksperimenata: {putanja}")
    print(pd.DataFrame(redovi).to_string(index=False))
    nacrtaj_krive_za_stope(krive)


# ============================================================================
# Glavni program
# ============================================================================
def main() -> None:
    """
    Čita opcije iz komandne linije i pokreće ili poređenje eksperimenata, ili
    jedno obučavanje sa ispisom mera, grafikonima i snimanjem modela.
    """
    # ovde zadajem opcije komandne linije; bez njih model uči sa α = 0.1 i najviše 25000 iteracija,
    # kao model iz izveštaja
    parser = argparse.ArgumentParser(description="Linearna regresija sa gradijentnim spustom.")
    parser.add_argument("--stopa_ucenja", type=float, default=0.1, help="stopa učenja α")
    parser.add_argument("--iteracije", type=int, default=25000, help="najveći broj iteracija")
    parser.add_argument("--regularizacija", type=float, default=0.0, help="L2 parametar λ")
    parser.add_argument("--udeo_testa", type=float, default=0.2, help="udeo test skupa")
    parser.add_argument("--bez_log_cene", action="store_true",
                        help="učiti sirovu cenu umesto logaritma cene")
    parser.add_argument("--kategorija", default=None,
                        help="obučiti model samo za jednu kategoriju (npr. televizor)")
    parser.add_argument("--eksperimenti", action="store_true",
                        help="pokrenuti poređenje više podešavanja")
    argumenti = parser.parse_args()

    # uz --kategorija model učim samo na toj kategoriji, i to ako ima bar 50 proizvoda
    tabela = ucitaj_preciscene()
    if argumenti.kategorija:
        tabela = tabela[tabela["kategorija"] == argumenti.kategorija].reset_index(drop=True)
        print(f"[INFO] Samo kategorija '{argumenti.kategorija}': {len(tabela):,} proizvoda")
        if len(tabela) < 50:
            print("[GRESKA] Premalo proizvoda za obučavanje.")
            return

    # uz --eksperimenti samo poredim podešavanja i ne snimam model
    if argumenti.eksperimenti:
        pokreni_eksperimente(tabela, argumenti.udeo_testa)
        return

    # inače model obučavam jednom, ispisujem mere, crtam tri grafikona i snimam ga za aplikaciju
    rezultat = obuci(tabela,
                     stopa_ucenja=argumenti.stopa_ucenja,
                     broj_iteracija=argumenti.iteracije,
                     lambda_reg=argumenti.regularizacija,
                     log_cena=not argumenti.bez_log_cene,
                     udeo_testa=argumenti.udeo_testa)
    ispisi_rezultat(rezultat)
    nacrtaj_krivu_ucenja(rezultat)
    nacrtaj_predvidjeno_stvarno(rezultat)
    nacrtaj_najuticajnija(rezultat)
    snimi_model(rezultat)


if __name__ == "__main__":
    main()
