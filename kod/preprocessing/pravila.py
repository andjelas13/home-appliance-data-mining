#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pravila.py — Pravila za preprocesiranje podataka (Zadatak 2).

Opis:
Ovde su samo pravila za čišćenje (spiskovi, regularni izrazi i granice), a
obrada je u ciscenje.py. Pravila sam odvojila da bi se jedno pravilo moglo
dodati ili promeniti bez diranja koda obrade. Nazivi kategorija i
karakteristika pisani su malim slovima i bez kvačica, jer ih ciscenje.py
poredi sa normalizovanim tekstom.

Sadrži:
    1. KATEGORIJE, ZBIRNE_KATEGORIJE, KATEGORIJE_ZA_IZBACIVANJE,
       NAZIVI_ZA_IZBACIVANJE
           — svođenje kategorija na kontrolisani rečnik, zbirne kategorije
             čiju vrstu tražim u nazivu, kategorije koje nisu uređaji i
             pribor prepoznat po nazivu proizvoda
    2. SINONIMI, OPSEG_RE, SABLONSKE_VREDNOSTI, NAZIV_ATRIBUTA_MODEL,
       NAZIVI_REZOLUCIJE, NAZIVI_DIMENZIJA
           — nazivi iste karakteristike, vrednosti koje se ne koriste i
             atributi koji se obrađuju posebno
    3. STARA_SKALA, NOVA_SKALA, KATEGORIJE_NOVE_SKALE, OZNAKA_STARE_SKALE,
       OZNAKA_NOVE_SKALE, NAZIVI_ENERGETSKE_KLASE, ENERGETSKA_KLASA_RE
           — dve odvojene skale energetske klase i prepoznavanje klase
    4. OPSEZI, OPSEZI_PO_VRSTI, MINIMALNO_KARAKTERISTIKA
           — dozvoljeni opsezi vrednosti i najmanji broj popunjenih polja
"""

import re

# ============================================================================
# 1. KATEGORIJE
# ============================================================================
# Nazive sa sajtova ('Smart TV', 'Non-smart TV', 'Televizori') svodim na
# jedan naziv po vrsti uređaja. Pravila proveravam redom i prvo poklapanje
# odlučuje, pa uža pravila idu pre širih, a skupne kategorije na sam kraj.
#
# Format: (regularni izraz nad nazivom, kategorija, grupa)
# ----------------------------------------------------------------------------
KATEGORIJE = [
    # --- televizori ---
    # 'non.?smart' mi hvata i 'non-smart' i 'non smart'
    (r"\b(smart tv|non.?smart tv|televizor)",            "televizor",        "tv"),

    # --- rashladni uređaji ---
    # 'side by side' je frižider sa dvoje vrata, pa ga odmah šaljem u frizider
    (r"side by side",                                     "frizider",         "bela tehnika"),
    (r"\b(frizider|frizideri)\b",                         "frizider",         "bela tehnika"),
    (r"\b(zamrzivac|zamrzivaci)\b",                       "zamrzivac",        "bela tehnika"),
    (r"vitrin",                                           "rashladna_vitrina","bela tehnika"),

    # --- pranje ---
    # kombinovanu mašinu stavila sam prvu, jer bi je inače uhvatilo pravilo 'susenje vesa'
    (r"pranje i susenje vesa",                            "ves_masina_susilica", "bela tehnika"),
    (r"susenje vesa",                                     "susilica",         "bela tehnika"),
    (r"pranje vesa",                                      "ves_masina",       "bela tehnika"),
    (r"masin[ae] za sudove|masin[ae] za pranje sudova|sudomasin", "sudo_masina", "bela tehnika"),

    # --- kuvanje ---
    # \b ispred korena 'sporet' i 'rern' traži da reč tu počinje, a nastavak može biti bilo koji
    (r"\bsporet",                                         "sporet",           "bela tehnika"),
    # mikrotalasne stoje pre rerni, jer Gigatron piše „Samostojeće mikrotalasne rerne",
    # pa bi ih pravilo 'rern' inače odnelo u kategoriju rerna
    (r"mikrotalasn",                                      "mikrotalasna",     "bela tehnika"),
    (r"\brern",                                           "rerna",            "bela tehnika"),
    (r"(indukcion|ugradn)[a-z]* ploc|ploce",              "ugradna_ploca",    "bela tehnika"),
    (r"aspirator",                                        "aspirator",        "bela tehnika"),
    # kod bojlera je slovo j opciono, jer se na sajtovima piše i 'boler'
    (r"\bboj?ler",                                        "bojler",           "bela tehnika"),

    # --- klimatizacija i grejanje ---
    # 'klim[ae]' mi pokriva i 'klima' i 'klime'
    (r"klim[ae]",                                         "klima",            "klimatizacija"),
    (r"preciscivac|tretiranje vazduha",                   "preciscivac_vazduha", "klimatizacija"),
    # odvlaživače i ovlaživače vodim zajedno, pod jednom kategorijom
    (r"odvlaziv|ovlaziv",                                 "ovlazivac_vazduha","klimatizacija"),
    (r"ventilator",                                       "ventilator",       "klimatizacija"),
    (r"toplotn[ae] pump",                                 "toplotna_pumpa",   "klimatizacija"),
    # grejalice: obrazac hvata i „pec" i „peci", a uz njih TA peći, kotlove i grejna tela
    (r"radijator|grejalic|kamin|konvektor|\bpec\b|\bpeci\b|peci na |ta peci"
     r"|kotlov|grejna tela|^grejanje$",                   "grejalica",        "klimatizacija"),

    # --- mali kućni aparati ---
    # za ove sam uzimala korene reči ('pegl', 'cediljk', 'mesoreznic'), da uhvatim i jedninu i množinu
    (r"usisivac",                                         "usisivac",         "mali aparati"),
    (r"parocistac",                                       "parocistac",       "mali aparati"),
    (r"pegl|parne stanice",                               "pegla",            "mali aparati"),
    (r"espresso|mlinov[a-z]* za kafu|aparat[a-z]* za .*kafu|dzezv|mutilic", "aparat_za_kafu", "mali aparati"),
    (r"friteza|airfryer|air fryer",                       "friteza",          "mali aparati"),
    (r"blender|sokovni[kc]|cediljk",                         "blender",          "mali aparati"),
    (r"mikser|multipraktik|multipraktic|kuhinjski robot|seckalic",     "mikser",           "mali aparati"),
    (r"toster|sendvic",                                   "toster",           "mali aparati"),
    (r"mini pekar|pekar|multikuker|multicook|aparat[a-z]* za palacink|galet|vafl",
                                                       "mini_pekara",      "mali aparati"),
    (r"mesoreznic|mlevenje mesa",                         "masina_za_meso",   "mali aparati"),
    (r"kuvalo|kuvala za vodu",                            "kuvalo_za_vodu",   "mali aparati"),
    (r"kuhinjsk[ae] vag",                                 "kuhinjska_vaga",   "mali aparati"),
    (r"resoi|reso\b",                                     "reso",             "mali aparati"),
    (r"masin[ae] za sivenje",                             "masina_za_sivenje","mali aparati"),
    (r"rostilj|\bgril",                                 "rostilj",          "mali aparati"),
    (r"ledomat",                                         "ledomat",          "mali aparati"),
    (r"ugradni setovi",                                  "ugradni_set",      "bela tehnika"),

    # skupne kategorije bez uže vrste uređaja; stoje poslednje, da prvo
    # probaju sva određenija pravila iznad
    (r"aparati za kuvanje|kokice|sladoled|zavarivanje i vakuumiranje|pripremu i serviranje"
     r"|ostali aparati za pripremu hrane|dispanzer",
                                                       "ostali_kuhinjski_aparat", "mali aparati"),
    (r"^kucni aparati$",                                 "ostali_kucni_aparat", "mali aparati"),
]

# Zbirna kategorija sa sajta ne kaže vrstu uređaja: Gigatron pod „Kućni aparati" drži
# zajedno usisivače, ventilatore, pegle i paročistače. Za takve zapise vrstu tražim u
# nazivu proizvoda, istim pravilima kao iznad. Uz zbirnu kategoriju stoje grupe u koje
# zapis sme da pređe, pa 'NINJA ... pica peć' iz kuhinjskih aparata ne postaje grejalica.
ZBIRNE_KATEGORIJE = {
    "ostali_kucni_aparat":     {"mali aparati", "klimatizacija"},
    "ostali_kuhinjski_aparat": {"mali aparati"},
}

# Kategorije koje izbacujem pre pravila iznad: pribor, delovi i potrošni materijal.
# Samu reč 'filter' izostavila sam, jer bi ispali i „Aparati za filter kafu",
# pa su tu samo nazivi koji sigurno znače deo ('^filteri', 'zamenski filter').
KATEGORIJE_ZA_IZBACIVANJE = [
    r"oprema", r"dodat", r"^filteri", r"ugradni filter", r"zamenski filter",
    r"kese", r"kapsul", r"tablet", r"sredstv", r"nastavc", r"posuda",
    r"postolj", r"nosac", r"bokali", r"nozice", r"ploce za rezanje",
    r"flasic", r"^kafe$",
    # „Ručni frižideri" su uglavnom rashladne torbe i prenosivi hladnjaci za piknik,
    # pa ih ne vodim kao kućne aparate
    r"rucni frizider",
]

# Neki proizvodi stoje u kategoriji uređaja, a nisu uređaj: grejna fioka među
# rernama, okvir za ugradnju među mikrotalasnim, filteri među prečišćivačima
# vazduha, nastavci među mikserima, nosači i stalci među grejalicama. Njih
# prepoznajem po nazivu proizvoda. Kad naziv kaže da je proizvod „za prečišćivač",
# „za paročistač" ili „za mašinu" (HEPA uložak, krpa, dekorativni front), to je deo
# drugog uređaja, a stanica za pražnjenje je dodatak robot usisivaču.
# Kod filtera (?!.*usisivac) na početku čuva usisivač sa HEPA filterom, a (?! kaf)
# čuva „Aparat za filter kafu".
NAZIVI_ZA_IZBACIVANJE = [
    r"grejn[ae] fiok", r"okvir za ugradn",
    r"^(?!.*usisivac).*\bfilter\b(?! kaf)", r"predfilter", r"patrona", r"podloge za aromu",
    r"\bnastavak\b", r"\bnogari\b", r"\bnosac\b", r"\bstalak za\b", r"set za rostilj",
    r"\bza (preciscivac|parocistac|masinu)\b", r"stanica za praznjenje",
]

# ============================================================================
# 2. SINONIMI TEHNIČKIH KARAKTERISTIKA
# ============================================================================
# Ključ mi je kolona prečišćene baze, a vrednost (nazivi sa sajtova, jedinica mere).
# Nazive probam redom; važi prvi čija je vrednost u toj jedinici i u opsegu.
# Npr. kapacitet veš mašine piše se kao 'Kapacitet pranja', 'Kapacitet za pranje
# veša' ili 'Kapacitet punjenja', a sve to ide u jednu kolonu kapacitet_pranja_kg.
# ----------------------------------------------------------------------------
SINONIMI = {
    "dijagonala_inch":          (["dijagonala ekrana", "dijagonala", "velicina ekrana"], "inch"),
    "zapremina_l":              (["ukupna zapremina", "ukupna zapremina (neto)", "zapremina",
                                  "neto zapremina", "kapacitet", "kapacitet (neto)",
                                  "zapremina rerne", "kapacitet rerne",
                                  "zapremina posude", "kapacitet posude",
                                  "zapremina kese/posude", "zapremina kese",
                                  "zapremina rezervoara", "kapacitet rezervoara",
                                  "kapacitet rezervoara za vodu",
                                  # pogrešno otkucani nazivi iz izvora, namerno sam ih
                                  # ostavila da se ti zapisi ne izgube
                                  "kapacitet rezeorvara za vodu", "kapacitet rezorvoara",
                                  "bruto zapremina"], "l"),
    "zapremina_frizider_l":     (["zapremina frizidera", "zapremina rashladnog dela",
                                  "zapremina frizidera (neto)"], "l"),
    "zapremina_zamrzivac_l":    (["zapremina zamrzivaca", "zapremina zamrzivackog dela",
                                  "zapremina zamrzivaca (neto)"], "l"),
    # goli „kapacitet" stoji u tri grupe: kod veš mašine je u kg, kod frižidera
    # u litrima, a kod klime u BTU, pa svaka grupa prima samo svoju jedinicu
    "kapacitet_pranja_kg":      (["kapacitet pranja", "kapacitet za pranje vesa",
                                  "kapacitet punjenja", "kolicina vesa", "kapacitet"], "kg"),
    # kod sudo mašine se kapacitet punjenja piše u kompletima, pa ga i ovde probam
    "kapacitet_kompleta":       (["kapacitet punjenja", "broj kompleta posudja", "broj kompleta"], "kompleta"),
    "brzina_centrifuge":        (["brzina centrifuge", "maksimalna brzina centrifuge",
                                  "broj obrtaja centrifuge"], "obr/min"),
    # „Priključna snaga" je električna snaga celog uređaja, pa je vodim u istoj koloni;
    # toplotni učinak („toplotna snaga" kod šporeta na čvrsto gorivo) nije električna
    # snaga, pa ga ne uzimam
    "snaga_w":                  (["snaga", "snaga motora", "ulazna snaga", "nominalna snaga",
                                  "snaga (maksimalna)", "prikljucna snaga"], "w"),
    # kod klime isti naziv proveravam dva puta: jednom tražim BTU, a jednom kW;
    # Gigatron BTU piše pod nazivom 'kapacitet klima uredjaja'
    "kapacitet_hladjenja_btu":  (["kapacitet hladjenja", "rashladni ucinak", "kapacitet",
                                  "kapacitet klima uredjaja"], "btu"),
    "kapacitet_hladjenja_kw":   (["kapacitet hladjenja", "rashladni ucinak", "snaga hladjenja"], "kw"),
    "visina_cm":                (["visina", "visina uredjaja"], "cm"),
    "sirina_cm":                (["sirina", "sirina uredjaja"], "cm"),
    "dubina_cm":                (["dubina", "dubina uredjaja"], "cm"),
    # kod klime uzimam masu i buku unutrašnje jedinice, jer je ona u prostoriji
    "tezina_kg":                (["tezina", "neto tezina", "masa", "masa (neto)",
                                  "masa bez postolja", "masa unutrasnje jedinice"], "kg"),
    "nivo_buke_db":             (["nivo buke", "buka", "jacina zvuka",
                                  "nivo buke unutrasnje jedinice",
                                  "nivo buke (unutrasnja jedinica)"], "db"),
    "potrosnja_kwh":            (["potrosnja elektricne energije", "godisnja potrosnja energije",
                                  "potrosnja energije", "potrosnja el. energije",
                                  "potrosnja elektricne enegije"], "kwh"),
    # za broj programa i broj brzina uzimam samo cifre sa početka vrednosti
    "broj_programa":            (["broj programa", "programi", "broj programa pranja"], "broj"),
    "broj_brzina":              (["broj brzina", "brzine", "brzina"], "broj"),
}

# vrednost zapisana kao raspon ('1 kg - 8 kg', '19 - 64 dB', '51.1 - 56 cm', 'od 1.6 l do 2 l')
# ne daje jedan broj, pa je preskačem i probam sledeći naziv
OPSEG_RE = re.compile(r"^(?:od\s+)?\d+(?:[.,]\d+)?\s*[a-z]*\s*(?:-|–|do)\s*\d")

# Winwinova tabela ispod uvoznikove specifikacije služi za filtere prodavnice i ima
# podrazumevane (šablonske) vrednosti: 'Visina 187 cm' stoji kod 945 proizvoda, a
# uvoznikova lista na istoj strani tu visinu ne potvrđuje ni kod jednog. Parove za
# koje lista na istoj strani daje istu vrednost u manje od 10% slučajeva ne koristim.
SABLONSKE_VREDNOSTI = {
    "winwin": {
        ("visina", "187 cm"), ("zapremina", "204 l"), ("kapacitet", "82 l"),
        ("zapremina frizidera", "95 l"),
        ("zapremina zamrzivaca", "50 l"), ("zapremina zamrzivaca", "100 l"),
    },
}

# nazivi karakteristike sa oznakom modela; njoj dajem prednost u odnosu na naziv proizvoda
NAZIV_ATRIBUTA_MODEL = ["model", "oznaka modela", "sifra modela"]

# rezolucija ('1920 x 1080 px') ima dva broja, pa je obrađujem posebno
NAZIVI_REZOLUCIJE = ["rezolucija ekrana", "rezolucija u pikselima", "rezolucija"]

# polja sa sve tri spoljne dimenzije zajedno, npr. '17,2 cm x 7 cm x 16 cm'
# ili '(VxŠxD): 34,2 cm x 28,2 cm x 22,3 cm'; iz njih računam gabarit
NAZIVI_DIMENZIJA = ["dimenzije", "dimenzije proizvoda", "dimenzije uredjaja",
                    "dimenzije (sxvxd)", "dimenzije bez postolja", "dimenzije ploce (sxvxd)",
                    "dimenzije unutrasnje jedinice", "dimenzije unutrasnje jedinice (sxvxd)"]

# ============================================================================
# 3. ENERGETSKE SKALE
# ============================================================================
# U izvorima postoje dve skale koje se ne mogu porediti:
#   - stara: klase sa plusevima (A+++, A++, A+) i slova od A nadole; uz nju u
#            tekstu piše '(po prethodnoj klasifikaciji)'
#   - nova:  slova od A do G, uz koja u tekstu piše 'Novo'
# Skalu određujem ovim redom:
#   1) izričita oznaka u tekstu: 'Novo' je nova skala, a 'po prethodnoj
#      klasifikaciji' ili znak '+' u klasi stara;
#   2) golo slovo ('A') tumačim po vrsti uređaja, po spisku KATEGORIJE_NOVE_SKALE.
# Zvanično preslikavanje iz jedne u drugu ne postoji, pa ih ne spajam, a rang
# (redni broj klase u svojoj listi, 1 = najbolja) računam samo unutar skale.
# ----------------------------------------------------------------------------
# Klase sam poređala od najbolje ka najgoroj, pa mi mesto u listi daje rang.
# Staru listu sam produžila do G, da svako slovo koje ENERGETSKA_KLASA_RE može da
# vrati ima rang; u podacima stara skala ide do E (aspiratori, grejalice, klime i bojleri).
STARA_SKALA = ["A+++", "A++", "A+", "A", "B", "C", "D", "E", "F", "G"]
NOVA_SKALA  = ["A", "B", "C", "D", "E", "F", "G"]

# vrste uređaja kod kojih golo slovo znači novu skalu. Proverila sam ih na spojenim
# uređajima: kod njih jedan oglas piše golo slovo, a drugi isto slovo uz „Novo"
# (frižideri 124 puta, mašine za sudove 90, veš-mašine 37...). Kod aspiratora, šporeta
# i rerni isto poređenje daje „(po prethodnoj klasifikaciji)" (aspiratori 69 puta,
# šporeti 38, rerne 31), pa su oni na staroj.
KATEGORIJE_NOVE_SKALE = {
    "frizider", "zamrzivac", "rashladna_vitrina", "ves_masina",
    "ves_masina_susilica", "sudo_masina", "susilica", "televizor",
}

# tekst po kome prepoznajem staru, odnosno novu skalu, bez obzira na velika i mala slova
OZNAKA_STARE_SKALE = re.compile(r"po\s+preth|stara\s+klasifik|old", re.IGNORECASE)
OZNAKA_NOVE_SKALE = re.compile(r"\bnovo\b|nova\s+klasifik", re.IGNORECASE)

# nazivi karakteristike sa energetskom klasom, redom kojim ih probam: prvo opšta
# 'Energetska klasa', a kod klime, kad nje nema, 'Energetska klasa hlađenja'.
# 'Energetska klasa grejanja' nije na spisku i ne čitam je: to je druga oznaka, koja
# je ista kao klasa koju uzimam samo kod 101 od 264 klime koje imaju obe, a najčešće
# je za stepen lošija (A+ prema A++)
NAZIVI_ENERGETSKE_KLASE = ["energetska klasa", "energetska klasa hladjenja",
                           "energetski nivo", "energetska efikasnost"]
# Umesto \b proveravam da levo i desno nema slova ni cifre. Iza 'A+' nema granice
# reči (i '+' i razmak nisu slova), pa bi obrazac sa \b od 'A+' vratio samo 'A'.
ENERGETSKA_KLASA_RE = re.compile(r"(?<![A-Za-z0-9])(A\+{0,3}|[B-G])(?![A-Za-z0-9])")

# ============================================================================
# 4. DOZVOLJENI OPSEZI
# ============================================================================
# (donja, gornja) granica za očigledne greške u izvoru, npr. televizor od 500 inča.
# Tehničku vrednost van opsega ne popravljam nego postaje NULL, a zapis sa
# cenom van opsega odbacujem ceo.
# ----------------------------------------------------------------------------
OPSEZI = {
    # cene su u dinarima, a cenu ispod 300 dinara smatram greškom u izvoru
    "cena":                     (300, 5_000_000),
    "dijagonala_inch":          (10, 120),
    "zapremina_l":              (0.2, 900),
    "zapremina_frizider_l":     (5, 700),
    "zapremina_zamrzivac_l":    (2, 600),
    "kapacitet_pranja_kg":      (1, 25),
    "kapacitet_kompleta":       (4, 20),
    "brzina_centrifuge":        (400, 2000),
    "snaga_w":                  (5, 15_000),
    "kapacitet_hladjenja_btu":  (5_000, 60_000),
    "kapacitet_hladjenja_kw":   (1, 20),
    "visina_cm":                (2, 250),
    "sirina_cm":                (2, 250),
    "dubina_cm":                (2, 250),
    "tezina_kg":                (0.1, 400),
    "nivo_buke_db":             (10, 100),
    "potrosnja_kwh":            (0.01, 2000),
    "broj_programa":            (1, 40),
    "broj_brzina":              (1, 30),
    # gabarit je proizvod tri dimenzije, pa mu je gornja granica mnogo veća
    "gabarit_cm3":              (50, 5_000_000),
    "rezolucija_sirina_px":     (320, 10_000),
    "rezolucija_visina_px":     (240, 10_000),
}

# Neke granice zavise od vrste uređaja: usisivač od 51,3 kg ili mašina za sudove
# od 359 kg su greške u izvoru, a šporet na čvrsto gorivo od 241 kg nije. Isto tako
# frižider visine '2,03 cm' ili ploča snage '5.8 W' imaju pogrešnu jedinicu. Ključ je
# kategorija ili grupa; granica kategorije ima prednost nad granicom grupe, a
# za ostalo važi granica iz OPSEZI.
VELIKE_DIMENZIJE = {"visina_cm": (20, 250), "sirina_cm": (20, 250), "dubina_cm": (20, 250)}
OPSEZI_PO_VRSTI = {
    "mali aparati":        {"tezina_kg": (0.1, 50)},
    "bela tehnika":        {"tezina_kg": (0.1, 250), "cena": (1_000, 5_000_000)},
    "frizider":            VELIKE_DIMENZIJE,
    "zamrzivac":           VELIKE_DIMENZIJE,
    "ves_masina":          VELIKE_DIMENZIJE,
    "ves_masina_susilica": VELIKE_DIMENZIJE,
    "susilica":            VELIKE_DIMENZIJE,
    "sudo_masina":         VELIKE_DIMENZIJE,
    "rerna":               VELIKE_DIMENZIJE,
    "ugradna_ploca":       {"snaga_w": (500, 15_000)},
}

# Zadatak 2 traži da se odbace zapisi bez dovoljno popunjenih atributa. Granicu
# sam stavila na 3 tehnička polja (energetska klasa se ne broji), da ostanu i
# jednostavni uređaji poput tostera. Menja se opcijom --min_karakteristika.
MINIMALNO_KARAKTERISTIKA = 3
