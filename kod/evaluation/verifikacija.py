#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verifikacija.py — Provera tačnosti samostalno napisanih algoritama.

Opis:
Projektni zadatak ne dozvoljava gotove biblioteke za obučavanje modela, ali
dozvoljava da se njima proveri tačnost sopstvenih rezultata. Skripta pokreće
moje implementacije i odgovarajuće funkcije iz scikit-learn nad istim podacima
i upoređuje rezultate. Poređenje ispisuje i snima u tekstualni izveštaj.

Šta se proverava:

    1. Linearna regresija  — sopstveni gradijentni spust naspram
                             sklearn.linear_model.LinearRegression i Ridge
                             (R² na test skupu i najveći apsolutni
                             koeficijent, na šest podela 80/20)
       1a. Gradijent i spust — gradijent naspram numeričkog izvoda i spust
                             naspram tačnog rešenja np.linalg.lstsq na
                             matrici punog ranga

    2. K-srednjih vrednosti — sopstveni K-means naspram sklearn.cluster.KMeans
                             (inercija i podudarnost dodela), i
                             sopstveni Silhouette naspram silhouette_score

    3. Kosinusna sličnost   — sopstvena formula naspram
                             sklearn.metrics.pairwise.cosine_similarity
                             (najveća apsolutna razlika po svim parovima)

    4. TF-IDF               — sopstvena implementacija naspram
                             sklearn.feature_extraction.text.TfidfVectorizer
                             (poklapanje Top-5 najsličnijih naziva)

Očekivane razlike:
Kosinusna sličnost je ista formula, pa razlika sme biti samo na nivou mašinske
preciznosti (ispod 1e-15). TF-IDF iz scikit-learn drugačije računa idf, pa se
porede preporuke, a ne same vrednosti; sličnosti se pre poređenja zaokružuju na
12 decimala, pa obe strane nazive sa jednakom sličnošću ređaju istim redom, inače
bi se liste razlikovale samo zbog redosleda jednakih.
K-means zavisi od početnih centara, pa dve implementacije mogu naći različite,
podjednako dobre rasporede. Regresiju poredim na šest podela, jer jedna podela
može slučajno da ispadne naročito dobra ili loša.

Ulazi:
    šema preciscena

Izlazi:
    izvestaj/modeli/verifikacija.txt             — tekstualni izveštaj o proveri

Primer poziva:
    python verifikacija.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# scikit-learn treba samo ovoj skripti, za poređenje; bez njega odmah stajem sa porukom umesto greške usred rada
if importlib.util.find_spec("sklearn") is None:
    print("[GRESKA] scikit-learn nije instaliran, a ova skripta poredi moje modele sa njim (vidi kod/requirements.txt).")
    sys.exit(1)

# dodajem u putanju folder models (podaci, regresija, kmeans, preporuke) i folder kod
# (zajednicko), da bih mogla da uvezem svoje module bez instaliranja paketa
sys.path.append(str(Path(__file__).resolve().parents[1] / "models"))
sys.path.append(str(Path(__file__).resolve().parents[1]))

# ovde uvozim svoje ručno napisane funkcije, a sklearn uvozim tek unutar svake provere
from podaci import Priprema, ucitaj_preciscene, podeli
from regresija import (dodaj_slobodni_clan, funkcija_troska, gradijent,
                       gradijentni_spust, predvidi, r2_skor)
import kmeans as moj_kmeans
import preporuke as moje_preporuke
from zajednicko.putanje import FOLDER_MODELA

# izlazni fajl verifikacija.txt držim u folderu modela, pored ostalih rezultata modela
IZLAZ = FOLDER_MODELA / "verifikacija.txt"

# ovo su mi semena za šest podela 80/20 na kojima poredim regresiju; 2026 je ista
# podela kao u regresija.py, a ITERACIJA_PROVERE je najveći broj iteracija mog spusta
SEMENA_PODELE = [2026, 1, 7, 42, 123, 999]
ITERACIJA_PROVERE = 8000


def hilj(broj: int) -> str:
    """Vraća ceo broj sa tačkom kao razdvajačem hiljada (8.000), kako se piše na srpskom."""
    # Python stavlja zarez za hiljade, pa ga ja samo zamenim tačkom
    return f"{broj:,}".replace(",", ".")


def zarez(vrednost: float, decimala: int) -> str:
    """Vraća broj sa decimalnim zarezom (0,85 umesto 0.85), za rečenice u izveštaju o proveri."""
    # prvo zaokružim na zadati broj decimala, pa tačku pretvorim u zarez
    return f"{vrednost:.{decimala}f}".replace(".", ",")

# u ovu listu skupljam sve ispisane redove, da ih na kraju upišem u verifikacija.txt
izvestaj: list[str] = []


def zapisi(red: str = "") -> None:
    """Ispisuje red na ekran i dodaje ga u listu izvestaj, za tekstualni izveštaj."""
    # jedan poziv mi radi dve stvari: vidim red odmah i ne moram posebno da ga pamtim za fajl
    print(red)
    izvestaj.append(red)


def naslov(tekst: str) -> None:
    """Zapisuje naslov odeljka između dve linije od znakova =, sa praznim redom ispred."""
    # linija od 78 znakova = da se odeljci lepo razdvoje i na ekranu i u .txt fajlu
    zapisi()
    zapisi("=" * 78)
    zapisi(tekst)
    zapisi("=" * 78)


# ============================================================================
# 1. Linearna regresija
# ============================================================================
def proveri_regresiju(tabela: pd.DataFrame) -> None:
    """
    Na šest podela 80/20 obučava moj gradijentni spust, LinearRegression i Ridge
    nad istom matricom i poredi R² na testu (u log prostoru) i najveći koeficijent.
    Meri i rang i uslovljenost matrice i ispisuje tumačenje.
    """
    # LinearRegression je isti onaj sa vežbi, a ovde mi služi samo da
    # proverim da li moj gradijentni spust daje razuman R²
    from sklearn.linear_model import LinearRegression, Ridge

    naslov("1. LINEARNA REGRESIJA — sopstveni gradijentni spust vs. scikit-learn")

    # ------------------------------------------------------------------
    # Istu tabelu delim na trening i test na šest nasumičnih načina, jer jedna
    # podela može slučajno da ispadne sjajna ili loša, pa zaključak ne bi važio.
    # ------------------------------------------------------------------
    rezultati = []
    for seme in SEMENA_PODELE:
        # moja funkcija podeli radi isto što i train_test_split, samo što ja
        # mešam redove i uzimam 80/20 sa fiksnim semenom, a na vežbama je bilo 75/25 bez
        # mešanja (shuffle=False)
        indeksi_trening, indeksi_test = podeli(len(tabela), 0.2, seme)
        trening = tabela.iloc[indeksi_trening].reset_index(drop=True)
        test = tabela.iloc[indeksi_test].reset_index(drop=True)

        # pripremu učim samo na treningu ove podele, kao u regresija.py, da test
        # ostane neviđen; cilj mi je logaritam cene i za trening i za test
        priprema = Priprema()
        X_trening, nazivi = priprema.nauci_i_primeni(trening)
        X_test = priprema.primeni(test)
        y_trening = np.log(trening["cena_min"].to_numpy(dtype=float))
        y_test = np.log(test["cena_min"].to_numpy(dtype=float))

        # brojim kolone interakcije koje su unutar svoje kategorije konstantne: kategorija nema tu
        # karakteristiku, pa je popunjena jednom medijanom i kolona ponavlja one-hot kolonu kategorije
        kategorija_reda = trening["kategorija"].astype(str).to_numpy()
        konstantnih = 0
        for kolona, naziv_kolone in enumerate(nazivi):
            if "×" in naziv_kolone:
                vrednosti = X_trening[kategorija_reda == naziv_kolone.split("×")[1], kolona]
                konstantnih += int(len(vrednosti) > 0 and vrednosti.min() == vrednosti.max())

        # moj gradijentni spust: stopa učenja 0,1 i stroži prag zaustavljanja nego
        # inače, a ispis iteracija gasim da ne zatrpa izveštaj
        theta, _ = gradijentni_spust(dodaj_slobodni_clan(X_trening), y_trening,
                                     stopa_ucenja=0.1, broj_iteracija=ITERACIJA_PROVERE,
                                     prag_zaustavljanja=1e-12, ispisuj=False)
        moja_predikcija = predvidi(dodaj_slobodni_clan(X_test), theta)

        # bibliotečke verzije: najmanji kvadrati i Ridge (L2, λ = 0,1, koji se u
        # scikit-learn zove alpha); slobodni član dodaju same, kao intercept_ na vežbama,
        # pa im ja ne dodajem kolonu jedinica
        najmanji_kvadrati = LinearRegression().fit(X_trening, y_trening)
        greben = Ridge(alpha=0.1).fit(X_trening, y_trening)

        # uslovljenost računam kao najveću / najmanju singularnu vrednost; ogroman broj
        # mi znači da je matrica skoro singularna, a rang manji od broja kolona da je kolinearna
        singularne = np.linalg.svd(X_trening, compute_uv=False)
        # za svaku podelu pamtim jedan rečnik; sve tri metode merim svojim r2_skor,
        # koji računa isti R² kao model.score, samo ručno
        rezultati.append({
            "seme":         seme,
            "kolona":       int(X_trening.shape[1]),
            "rang":         int(np.linalg.matrix_rank(X_trening)),
            "konstantnih_interakcija": konstantnih,
            "uslovljenost": float(singularne[0] / singularne[-1]),
            "gd_r2":        r2_skor(y_test, moja_predikcija),
            "gd_koef":      float(np.abs(theta[1:]).max()),
            "lr_r2":        r2_skor(y_test, najmanji_kvadrati.predict(X_test)),
            "lr_koef":      float(np.abs(najmanji_kvadrati.coef_).max()),
            "ridge_r2":     r2_skor(y_test, greben.predict(X_test)),
            "ridge_koef":   float(np.abs(greben.coef_).max()),
        })

    # ------------------------------------------------------------------
    # Ispis: tabela po podelama, rasponi R² i građa matrice
    # ------------------------------------------------------------------
    zapisi("Model uči logaritam cene; R² se računa u tom prostoru, na test skupu.")
    zapisi(f"Sopstveni gradijentni spust: stopa učenja 0,1, najviše {hilj(ITERACIJA_PROVERE)} iteracija.")
    zapisi()
    # zaglavlje i redovi imaju iste širine kolona, da mi se brojevi poravnaju ispod naslova
    zapisi(f"{'seme podele':>11} {'sopstveni GD':>13} {'LinearRegression':>17} {'Ridge λ=0,1':>12}"
           f" {'max koef. GD':>13} {'max koef. LR':>13}")
    for r in rezultati:
        zapisi(f"{r['seme']:>11} {r['gd_r2']:>13.4f} {r['lr_r2']:>17.4f} {r['ridge_r2']:>12.4f}"
               f" {r['gd_koef']:>13.2f} {r['lr_koef']:>13.2f}")

    # iz svih podela izvlačim R² mog spusta (gd) i LinearRegression (lr) i najveće koeficijente
    gd = [r["gd_r2"] for r in rezultati]
    lr = [r["lr_r2"] for r in rezultati]
    najveci_gd = max(r["gd_koef"] for r in rezultati)
    najveci_lr = max(r["lr_koef"] for r in rezultati)
    zapisi()
    zapisi(f"{'raspon R² — sopstveni GD':40} {min(gd):.4f} do {max(gd):.4f}")
    zapisi(f"{'raspon R² — LinearRegression':40} {min(lr):.4f} do {max(lr):.4f}")
    zapisi(f"{'najveći koeficijent — sopstveni GD':40} {najveci_gd:.2f}")
    zapisi(f"{'najveći koeficijent — LinearRegression':40} {najveci_lr:.2f}")
    zapisi()
    # za broj kolona, rang i uslovljenost ispisujem najmanju i najveću vrednost kroz podele
    zapisi("--- Građa matrice obeležja ---")
    zapisi(f"{'broj kolona':40} {min(r['kolona'] for r in rezultati)} do {max(r['kolona'] for r in rezultati)}")
    zapisi(f"{'rang matrice':40} {min(r['rang'] for r in rezultati)} do {max(r['rang'] for r in rezultati)}")
    zapisi(f"{'konstantnih kolona interakcije':40} {min(r['konstantnih_interakcija'] for r in rezultati)}"
           f" do {max(r['konstantnih_interakcija'] for r in rezultati)}")
    zapisi(f"{'uslovljenost (cond)':40} {min(r['uslovljenost'] for r in rezultati):.1e}"
           f" do {max(r['uslovljenost'] for r in rezultati):.1e}")
    zapisi()

    # ------------------------------------------------------------------
    # Tumačenje sastavljam iz izmerenih brojeva, a ne pišem unapred,
    # da tekst ne tvrdi nešto što podaci ne pokazuju.
    # ------------------------------------------------------------------
    # kolinearnost navodim samo ako je rang manji od broja kolona na svakoj podeli
    kolinearna = all(r["rang"] < r["kolona"] for r in rezultati)
    if kolinearna:
        zapisi("Matrica je izrazito kolinearna, i to je očekivano. Najveći deo ranga gube kolone")
        zapisi("interakcije za karakteristike koje kategorija uopšte nema: popunjene su jednom")
        zapisi("medijanom, pa unutar kategorije ponavljaju njenu one-hot kolonu. Uz to, pošto svaki")
        zapisi("proizvod pripada tačno jednoj kategoriji, zbir svih kolona interakcije jedne")
        zapisi("karakteristike jednak je samoj toj karakteristici, a zbir one-hot kolona je jedinica.")
        zapisi("Zato postoji beskonačno mnogo različitih vektora koeficijenata koji na skupu")
        zapisi("za treniranje daju isto predviđanje.")
    else:
        zapisi("Rang matrice je bar na jednoj podeli jednak broju kolona, pa matrica nije")
        zapisi("kolinearna na svim podelama.")
    zapisi()
    # najmanje kvadrate smatram nestabilnim ako im je raspon R² kroz podele više od
    # tri puta veći nego kod mog spusta i ako im je najlošiji R² ispod mog najlošijeg
    nestabilna = (max(lr) - min(lr)) > 3 * (max(gd) - min(gd)) and min(lr) < min(gd)
    if nestabilna:
        # u ovoj grani objašnjavam zašto moj spust ispada stabilniji, a brojeve
        # ubacujem iz izmerenih raspona, sa decimalnim zarezom
        zapisi("Metoda najmanjih kvadrata je na takvoj matrici NESTABILNA: zavisno od podele,")
        zapisi(f"R² joj se kreće od {zarez(min(lr), 2)} do {zarez(max(lr), 2)}, a koeficijenti rastu i do {najveci_lr:.0f}.")
        zapisi(f"Sopstveni gradijentni spust je na svim podelama između {zarez(min(gd), 2)} i {zarez(max(gd), 2)},")
        # najveći koeficijent ispisujem na dve decimale, koliko ih ima i tabela iznad,
        # da se ta dva broja poklope
        zapisi(f"a najveći koeficijent mu je {zarez(najveci_gd, 2)}.")
        zapisi()
        zapisi("Zašto: metoda najmanjih kvadrata vraća rešenje najmanje norme, ali matrica ima i")
        zapisi("pravce koje podaci određuju tek neznatno (vrlo male singularne vrednosti, npr. retki")
        zapisi("brendovi i kategorije). U tim pravcima najmanji kvadrati daju ogromne koeficijente")
        zapisi("koji ne važe na novim podacima. Gradijentni spust polazi od nule i u tim pravcima se")
        zapisi(f"za {hilj(ITERACIJA_PROVERE)} iteracija gotovo ne pomeri, pa se ponaša kao da je regularizovan")
        zapisi("(rani prekid), iako to nije izričito zadato; cena toga je nešto veća greška na")
        zapisi("skupu za treniranje. Ridge, koji takvu regularizaciju ima izričito, daje R²")
        zapisi(f"od {zarez(min(r['ridge_r2'] for r in rezultati), 2)} do {zarez(max(r['ridge_r2'] for r in rezultati), 2)} — "
               f"znatno ujednačenije od metode najmanjih kvadrata,")
        zapisi("što pokazuje da je razlika posledica regularizacije. Da je sam kod tačan,")
        zapisi("proverava odeljak 1a.")
    else:
        # ako su obe metode slične, samo navedem oba raspona R²
        zapisi(f"Na ovim podelama obe metode daju slične rezultate (sopstvena {zarez(min(gd), 2)}–{zarez(max(gd), 2)},")
        zapisi(f"bibliotečka {zarez(min(lr), 2)}–{zarez(max(lr), 2)}), što potvrđuje ispravnost implementacije.")



def proveri_gradijent_i_spust(tabela: pd.DataFrame) -> None:
    """
    Proverava samu implementaciju, bez uticaja kolinearnosti prave matrice:
        1) gradijent poredi sa numeričkim izvodom (J(θ + h) − J(θ − h)) / 2h,
        2) spust na matrici punog ranga (samo numeričke kolone i slobodni član)
           poredi sa tačnim rešenjem najmanjih kvadrata iz np.linalg.lstsq.
    """
    naslov("1a. GRADIJENT I SPUST — provera same implementacije")

    # uzimam trening deo podele 2026, kao u regresija.py
    indeksi_trening, _ = podeli(len(tabela), 0.2, 2026)
    trening = tabela.iloc[indeksi_trening].reset_index(drop=True)
    priprema = Priprema()
    X, _ = priprema.nauci_i_primeni(trening)
    y = np.log(trening["cena_min"].to_numpy(dtype=float))

    # 1) za 20 nasumičnih parametara računam izvod pomeranjem θⱼ za ±h, bez i sa L2 kaznom
    X_ceo = dodaj_slobodni_clan(X)
    generator = np.random.default_rng(2026)
    theta = generator.normal(scale=0.1, size=X_ceo.shape[1])
    h = 1e-6
    for lambda_reg in (0.0, 2.0):
        moj = gradijent(X_ceo, y, theta, lambda_reg)
        najveca_razlika = 0.0
        for j in generator.choice(X_ceo.shape[1], 20, replace=False):
            pomak = np.zeros(X_ceo.shape[1])
            pomak[j] = h
            numericki = (funkcija_troska(X_ceo, y, theta + pomak, lambda_reg)
                         - funkcija_troska(X_ceo, y, theta - pomak, lambda_reg)) / (2 * h)
            najveca_razlika = max(najveca_razlika, abs(numericki - moj[j]))
        zapisi(f"{'gradijent − numerički izvod, λ = ' + zarez(lambda_reg, 0):40} {najveca_razlika:.1e}")

    # 2) prve kolone matrice su standardizovane numeričke karakteristike; bez one-hot kolona i
    #    interakcija matrica je punog ranga, pa najmanji kvadrati imaju jedno rešenje
    X_pun = dodaj_slobodni_clan(X[:, :len(priprema.numericke)])
    theta_spust, _ = gradijentni_spust(X_pun, y, stopa_ucenja=0.1, broj_iteracija=20000,
                                       prag_zaustavljanja=0.0, ispisuj=False)
    theta_tacno = np.linalg.lstsq(X_pun, y, rcond=None)[0]
    zapisi(f"{'rang matrice numeričkih kolona':40} {np.linalg.matrix_rank(X_pun)} od {X_pun.shape[1]}")
    zapisi(f"{'najveća razlika θ (spust − lstsq)':40} {np.abs(theta_spust - theta_tacno).max():.1e}")
    zapisi()
    zapisi("Gradijent se poklapa sa numeričkim izvodom do greške samog numeričkog računa, a na")
    zapisi("matrici punog ranga spust stiže do tačnog rešenja najmanjih kvadrata. Implementacija")
    zapisi("je dakle tačna, a razlike iz odeljka 1 potiču od kolinearnosti i ranog prekida.")


# ============================================================================
# 2. K-srednjih vrednosti
# ============================================================================
def proveri_kmeans(tabela: pd.DataFrame) -> None:
    """
    Na frižiderima poredi moj K-means sa KMeans iz scikit-learn za K = 3 do 6,
    preko inercije i podudarnosti dodela. Za K iz primera (4) poredi i moj Silhouette sa
    silhouette_score iz scikit-learn, nad istom podelom na klastere.
    """
    # KMeans je isti onaj sa vežbi; ovde ga ne koristim za rezultat,
    # nego samo da uporedim inerciju i dodele sa svojom implementacijom
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    naslov("2. K-SREDNJIH VREDNOSTI — sopstvena implementacija vs. scikit-learn")

    # oba algoritma dobijaju istu matricu: frižideri, tri obeležja, težine 50/30/20,
    # pripremljena mojom funkcijom pripremi_matricu
    obelezja = ["cena_min", "zapremina_l", "energetska_rang"]
    deo = tabela[tabela["kategorija"] == "frizider"].reset_index(drop=True)
    X, zadrzani = moj_kmeans.pripremi_matricu(deo, obelezja, [50, 30, 20])
    zapisi(f"Skup: frižideri, {hilj(len(zadrzani))} proizvoda, obeležja: {', '.join(obelezja)}")
    zapisi()

    zapisi(f"{'K':>3} {'inercija (moja)':>17} {'inercija (sklearn)':>19} "
           f"{'odnos':>8} {'podudarnost dodela':>20}")
    redovi = []
    # slično petlji sa KMeans(n_clusters=i) sa vežbi, samo što ja idem kroz
    # K = 3, 4, 5, 6 i za svako K poredim dve implementacije
    for k in (3, 4, 5, 6):
        # i moja funkcija i biblioteka (n_init) pokreću algoritam 10 puta i biraju najbolje
        moj = moj_kmeans.kmeans(X, k)
        njihov = KMeans(n_clusters=k, n_init=10, random_state=2026).fit(X)

        # oznake klastera su proizvoljne (moj klaster 0 može biti njihov 2), pa
        # podudarnost merim preko parova tačaka: da li ih obe podele stavljaju
        # zajedno ili obe odvojeno
        podudarnost = uporedi_dodele(moj["oznake"], njihov.labels_)

        # inertia_ iz biblioteke je isti broj koji se na vežbama skupljao za lakat,
        # pa odnos moje i njihove inercije blizu 1 znači da sam našla jednako dobar raspored
        zapisi(f"{k:>3} {moj['inercija']:>17,.2f} {njihov.inertia_:>19,.2f} "
               f"{moj['inercija'] / njihov.inertia_:>8.4f} {podudarnost:>19.1%}")
        redovi.append({"k": k, "inercija_moja": round(float(moj["inercija"]), 2),
                       "inercija_sklearn": round(float(njihov.inertia_), 2),
                       "odnos": round(float(moj["inercija"] / njihov.inertia_), 4),
                       "podudarnost": round(podudarnost, 4), "oznake": moj["oznake"]})

    zapisi()
    zapisi("Inercija je zbir kvadrata rastojanja do centara — manja je bolja.")
    zapisi("Odnos blizu 1,0 znači da su oba postupka našla podjednako dobar raspored.")
    zapisi("Oznake klastera su proizvoljne, pa se podudarnost meri preko parova tačaka:")
    zapisi("koliki procenat parova obe implementacije svrstavaju isto (zajedno ili odvojeno).")

    # objašnjenje dodajem samo za K gde je moja inercija veća za više od 1%
    losiji = [r for r in redovi if r["odnos"] > 1.01]
    if losiji:
        zapisi()
        # K-ove i procente nabrajam u jednoj rečenici, da objašnjenje ispod ne visi
        spisak_k = " i ".join(f"K = {r['k']}" for r in losiji)
        veca_inercija = " i ".join(zarez(100 * (r["odnos"] - 1), 1) + "%" for r in losiji)
        zapisi(f"Za {spisak_k} sopstvena implementacija ima {veca_inercija} veću inerciju. Obe")
        zapisi("biraju najbolje od 10 pokretanja, ali sa različitim početnim centrima, pa za veći")
        zapisi("broj klastera mogu da završe u različitim lokalnim minimumima.")

    # Silhouette računam za isti K kao u primeru iz izveštaja (pokreni.bat klasteri): uzimam
    # istu svoju podelu na klastere i računam ga
    # i svojom formulom i sa silhouette_score, da razlika bude samo u formuli
    k_primera = 4
    podela_primera = next(r for r in redovi if r["k"] == k_primera)["oznake"]
    moj_silhouette = moj_kmeans.silhouette(X, podela_primera)
    njihov_silhouette = silhouette_score(X, podela_primera)
    zapisi()
    zapisi(f"Silhouette koeficijent za K = {k_primera}, nad istom podelom na klastere:")
    zapisi(f"{'sopstvena formula':40} {moj_silhouette:.10f}")
    zapisi(f"{'silhouette_score — scikit-learn':40} {njihov_silhouette:.10f}")
    zapisi(f"{'apsolutna razlika':40} {abs(moj_silhouette - njihov_silhouette):.3e}")
    # moja funkcija računa na uzorku od 2.000 samo kad tačaka ima više, a
    # biblioteka uvek na svim tačkama, pa tada mala razlika nije greška
    if len(X) > 2000:
        zapisi("Sopstvena funkcija računa na uzorku od 2.000 tačaka, pa se vrednosti razlikuju malo.")
    else:
        zapisi("Sopstvena funkcija računa na uzorku od 2.000 tačaka kada ih je više; ovde ih je")
        zapisi("manje, pa obe strane računaju nad svim tačkama.")



def uporedi_dodele(moje: np.ndarray, njihove: np.ndarray, uzorak: int = 1500,
                   seme: int = 2026) -> float:
    """
    Meri podudarnost dve podele na klastere preko parova tačaka (Rand indeks).
    Vraća udeo parova koje obe podele svrstavaju isto, zajedno ili odvojeno, pa
    proizvoljne oznake klastera ne smetaju. Za više od 1.500 tačaka radi na uzorku.
    """
    # kad tačaka ima više od 1.500 (uzorak), za obe podele uzimam isti nasumični izbor,
    # da matrica parova ispod ne bude prevelika
    generator = np.random.default_rng(seme)
    if len(moje) > uzorak:
        izbor = generator.choice(len(moje), uzorak, replace=False)
        moje, njihove = moje[izbor], njihove[izbor]

    # ovde pravim matrice True/False: da li su tačke i i j u istom klasteru
    zajedno_kod_mene = moje[:, None] == moje[None, :]
    zajedno_kod_njih = njihove[:, None] == njihove[None, :]

    # gledam samo parove iznad dijagonale, da se svaki par broji jednom i bez tačke same sa sobom
    gornji_trougao = np.triu_indices(len(moje), k=1)
    return float((zajedno_kod_mene[gornji_trougao] == zajedno_kod_njih[gornji_trougao]).mean())


# ============================================================================
# 3. Kosinusna sličnost
# ============================================================================
def proveri_kosinusnu_slicnost() -> None:
    """
    Poredi moju kosinusnu sličnost sa cosine_similarity iz scikit-learn na 200
    nasumičnih vektora dužine 40 i ispisuje najveću i prosečnu razliku.
    """
    from sklearn.metrics.pairwise import cosine_similarity

    naslov("3. KOSINUSNA SLIČNOST — sopstvena formula vs. scikit-learn")

    # ne treba mi baza za ovu proveru: pravim nasumične vektore iz normalne
    # raspodele, sa fiksnim semenom da rezultat bude isti pri svakom pokretanju
    generator = np.random.default_rng(2026)
    A = generator.normal(size=(200, 40))

    # svoju matricu sličnosti slažem red po red: svaki vektor prema svim ostalim,
    # pa redove naslažem jedan na drugi i oduzmem od bibliotečke matrice
    moja = np.vstack([moje_preporuke.kosinusna_slicnost_prema_svima(red, A) for red in A])
    njihova = cosine_similarity(A)
    razlika = np.abs(moja - njihova)

    zapisi(f"Testirano na {A.shape[0]} nasumičnih vektora dimenzije {A.shape[1]} "
           f"({hilj(A.shape[0] ** 2)} parova).")
    zapisi(f"{'najveća apsolutna razlika':40} {razlika.max():.3e}")
    zapisi(f"{'prosečna apsolutna razlika':40} {razlika.mean():.3e}")
    zapisi()

    # proveravam i samu funkciju kosinusna_slicnost, na paru prva dva vektora
    a, b = A[0], A[1]
    zapisi(f"{'kosinusna_slicnost(a, b) — sopstvena':40} {moje_preporuke.kosinusna_slicnost(a, b):.12f}")
    zapisi(f"{'cosine_similarity — scikit-learn':40} {float(cosine_similarity([a], [b])[0][0]):.12f}")
    zapisi()
    zapisi("Reč je o istoj matematičkoj formuli, pa se rezultati moraju poklopiti do")
    zapisi("mašinske preciznosti; razlika ispod 1e-15 je posledica zaokruživanja.")


# ============================================================================
# 4. TF-IDF
# ============================================================================
def proveri_tfidf(tabela: pd.DataFrame) -> None:
    """
    Na prvih 400 naziva televizora poredi moj TF-IDF sa TfidfVectorizer, uz isti
    tokenizator, i meri koliko se poklapa Top-5 najsličnijih naziva.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    naslov("4. TF-IDF — sopstvena implementacija vs. scikit-learn")

    # uzimam nazive televizora kao tekst, i to prvih 400, da provera bude brza
    nazivi = (tabela[tabela["kategorija"] == "televizor"]["naziv"]
              .astype(str).head(400).tolist())

    # moja klasa TfIdf prvo nauči rečnik i idf na nazivima, pa od njih napravi matricu
    moj = moje_preporuke.TfIdf()
    moj.nauci(nazivi)
    moja_matrica = moj.matrica(nazivi)

    # biblioteci dajem moj tokenizator rastavi_na_reci; mala slova on već pravi,
    # pa je lowercase=False, a token_pattern=None jer se regex tada ne koristi
    vektorizator = TfidfVectorizer(tokenizer=moje_preporuke.rastavi_na_reci,
                                   lowercase=False, token_pattern=None)
    njihova_matrica = vektorizator.fit_transform(nazivi).toarray()

    # veličine rečnika ispisujem da vidim da li obe strane izdvajaju isto toliko reči
    zapisi(f"Skup: {len(nazivi)} naziva televizora")
    zapisi(f"{'veličina rečnika — sopstvena':40} {len(moj.recnik)}")
    zapisi(f"{'veličina rečnika — scikit-learn':40} {len(vektorizator.vocabulary_)}")
    zapisi()

    # idf se računa malo drugačije (scikit-learn dodaje 1 i u brojilac), pa ne poredim vrednosti,
    # nego da li obe matrice daju iste najsličnije nazive; sličnost za obe računam istom
    # funkcijom, jer ovde proveravam TF-IDF, a ne kosinus. Nazivi koji su po sličnosti jednaki
    # razlikuju se u računu tek na 16. decimali, pa bi ih redosled razdvojio slučajno: zato
    # sličnosti zaokružujem na 12 decimala, a jednake ostavljam redom naziva (kind="stable");
    # sam naziv isključujem sa -inf na dijagonali
    moje_sirove = cosine_similarity(moja_matrica)
    njihove_sirove = cosine_similarity(njihova_matrica)
    np.fill_diagonal(moje_sirove, -np.inf)
    np.fill_diagonal(njihove_sirove, -np.inf)
    moje_slicnosti = np.round(moje_sirove, 12)
    njihove_slicnosti = np.round(njihove_sirove, 12)

    # argsort(−sličnost) mi ređa od najsličnijeg, a kind="stable" jednake ostavlja redom naziva,
    # isto u obe matrice; uzimam prvih pet, a poklapanje = zajednički / 5. Isto merim i nad
    # nezaokruženim sličnostima, da se vidi koliko na poklapanje utiče sam korak zaokruživanja.
    poklapanja = []
    poklapanja_bez_zaokruzivanja = []
    for redni_broj in range(len(nazivi)):
        moj_red = np.argsort(-moje_slicnosti[redni_broj], kind="stable")[:5]
        njihov_red = np.argsort(-njihove_slicnosti[redni_broj], kind="stable")[:5]
        poklapanja.append(len(set(moj_red) & set(njihov_red)) / 5)
        moj_sirov = np.argsort(-moje_sirove[redni_broj], kind="stable")[:5]
        njihov_sirov = np.argsort(-njihove_sirove[redni_broj], kind="stable")[:5]
        poklapanja_bez_zaokruzivanja.append(len(set(moj_sirov) & set(njihov_sirov)) / 5)

    # na kraju ispisujem prosečno poklapanje i koliko naziva ima potpuno isti Top-5,
    # i to oba merenja jedno pod drugim
    zapisi(f"{'prosečno poklapanje Top-5 preporuka':40} {np.mean(poklapanja):.1%}")
    zapisi(f"{'nazivi sa potpuno istim Top-5':40} "
           f"{sum(1 for p in poklapanja if p == 1.0)} / {len(poklapanja)}")
    zapisi(f"{'poklapanje bez zaokruživanja':40} {np.mean(poklapanja_bez_zaokruzivanja):.1%}")
    zapisi(f"{'isti Top-5 bez zaokruživanja':40} "
           f"{sum(1 for p in poklapanja_bez_zaokruzivanja if p == 1.0)} / {len(poklapanja_bez_zaokruzivanja)}")
    zapisi()
    zapisi("Vrednosti idf-a se razlikuju jer scikit-learn (smooth_idf) računa ln((1+N)/(1+df)) + 1,")
    zapisi("a moja formula ln(N/(1+df)) + 1, pa se ne porede sami brojevi nego ono što")
    zapisi("je za preporuke jedino važno — redosled najsličnijih proizvoda. Pre poređenja obe")
    zapisi("sličnosti zaokružujem na 12 decimala, pa nazivi sa jednakom sličnošću u obe liste")
    zapisi("ostaju redom naziva. Bez tog koraka poklapanje je manje samo zato što se jednako")
    zapisi("slični nazivi razlikuju tek na 16. decimali, pa ispada slučajno koji je od njih")
    zapisi("peti, a koji šesti.")


# ============================================================================
# Glavni program
# ============================================================================
def main() -> None:
    """Pokreće sve četiri provere redom i na kraju upisuje sve ispisane redove u verifikacija.txt."""
    # na vrhu izveštaja naglasim da biblioteke koristim samo za proveru
    zapisi("PROVERA TAČNOSTI SAMOSTALNIH IMPLEMENTACIJA")
    zapisi("Gotove biblioteke se ovde koriste isključivo za verifikaciju,")
    zapisi("kako projektni zadatak i dozvoljava — ne za obučavanje modela.")

    # tabelu iz prečišćene baze čitam jednom i dajem je proverama kojima treba
    tabela = ucitaj_preciscene()
    zapisi(f"Podaci: {hilj(len(tabela))} proizvoda iz prečišćene baze")

    proveri_regresiju(tabela)
    proveri_gradijent_i_spust(tabela)
    proveri_kmeans(tabela)
    proveri_kosinusnu_slicnost()
    proveri_tfidf(tabela)

    # tek kad sve četiri provere prođu, sve skupljene redove upisujem u verifikacija.txt
    IZLAZ.parent.mkdir(parents=True, exist_ok=True)
    IZLAZ.write_text("\n".join(izvestaj), encoding="utf-8")
    print(f"\n[OK] Izveštaj o verifikaciji: {IZLAZ}")


if __name__ == "__main__":
    main()
