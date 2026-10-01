-- ============================================================================
-- upiti.sql — SQL upiti traženi u Zadatku 2 (analiza podataka)
--
-- Opis:
--   Svi upiti čitaju šemu preciscena, gde sam kategorije svela na rečnik,
--   karakteristike su brojevi, a isti uređaj iz dve prodavnice je jedan red.
--   Kao cenu svuda koristim cena_min, jer po najnižoj ceni kupac zaista može
--   da kupi uređaj.
--   Svaki upit ima oznaku @naziv, iz koje izvoz_rezultata.py pravi naziv lista.
--   Upite sam pisala tako da rade i u PostgreSQL-u, i u MySQL-u, i u kopiji baze
--   u SQLite fajlu, pa umesto COUNT(*) FILTER (WHERE ...) brojim sa
--   SUM(CASE WHEN ... THEN 1 ELSE 0 END), što je isto. Gde dva reda mogu imati
--   istu vrednost, u ORDER BY sam dodala i drugu kolonu, da redosled bude isti u svakoj bazi.
--
-- Pokretanje:
--   psql -h localhost -p 5433 -U psz -d psz_preciscena -f kod/analiza/upiti.sql
--   mysql -u root -p preciscena < kod/analiza/upiti.sql
--   ili python izvoz_rezultata.py, koji rezultate upisuje u Excel (rezultati_upita.xlsx).
-- ============================================================================


-- ----------------------------------------------------------------------------
-- UPIT 1: Broj proizvoda po kategorijama
-- @naziv: Proizvodi po kategorijama
-- ----------------------------------------------------------------------------
-- Grupišem po kategoriji i grupi, pa za svaku brojim proizvode i gledam
-- prosečnu, najnižu i najvišu cenu.
-- SUM(COUNT(*)) OVER () mi sabira brojeve svih grupa, tj. daje ukupan broj
-- proizvoda, pa je procenat udeo kategorije u celoj bazi
SELECT  kategorija,
        grupa,
        COUNT(*)                                                        AS broj_proizvoda,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)              AS procenat,
        ROUND(AVG(cena_min))                                            AS prosecna_cena,
        MIN(cena_min)                                                   AS najniza_cena,
        MAX(cena_min)                                                   AS najvisa_cena
FROM        preciscena.proizvodi
GROUP BY    kategorija, grupa
ORDER BY    broj_proizvoda DESC, kategorija;


-- ----------------------------------------------------------------------------
-- UPIT 2: Deset najzastupljenijih brendova po broju artikala
-- @naziv: Top 10 brendova
-- ----------------------------------------------------------------------------
-- Ovde ukupan broj uzimam podupitom (SELECT COUNT(*) ...), pa je procenat udeo
-- brenda u svim proizvodima, a broj_kategorija mi pokazuje u koliko različitih
-- vrsta uređaja brend ima artikle. Za isti broj proizvoda ređam po imenu brenda.
SELECT  brend,
        COUNT(*)                                                        AS broj_proizvoda,
        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM preciscena.proizvodi), 2) AS procenat,
        COUNT(DISTINCT kategorija)                                      AS broj_kategorija,
        ROUND(AVG(cena_min))                                            AS prosecna_cena
FROM        preciscena.proizvodi
GROUP BY    brend
ORDER BY    broj_proizvoda DESC, brend
LIMIT       10;


-- ----------------------------------------------------------------------------
-- UPIT 3 i 4: Proizvodi sa energetskom klasom C ili boljom, i zbirno
--         (odnosno A+ ili boljom po prethodnoj klasifikaciji)
-- @naziv: Energetska klasa C ili bolja
-- ----------------------------------------------------------------------------
-- Zadatak traži klasu C ili bolju (A+ ili bolju po staroj skali). Obe granice su
-- treće mesto na svojoj skali, pa sam uslov napisala isto za obe: energetska_klasa_num <= 3.
--     nova skala:   A(1)   B(2)   C(3)   D  E  F  G
--     stara skala:  A+++(1) A++(2) A+(3) A  B  C  D  E  — u podacima ide do E (rang 8)
-- Tako skale ne poredim međusobno, a zapisi bez poznate klase (rang NULL) ne ulaze.
-- Klase ređam po MIN(energetska_klasa_num), jer rang nije u GROUP BY.
SELECT  energetska_skala,
        energetska_klasa,
        COUNT(*)                                                        AS broj_proizvoda
FROM        preciscena.proizvodi
WHERE       energetska_klasa_num IS NOT NULL
  AND       energetska_klasa_num <= 3
GROUP BY    energetska_skala, energetska_klasa
ORDER BY    energetska_skala, MIN(energetska_klasa_num);

-- UPIT 4 (zbirno uz upit 3)
-- @naziv: Energetska klasa - zbirno
-- zbirno: brojim proizvode sa klasom C ili boljom i računam njihov udeo među onima
-- kojima je rang poznat (energetska_klasa_num nije NULL)
-- NULLIF sam stavila da ne delim nulom ako nijedan proizvod nema poznatu klasu
SELECT  SUM(CASE WHEN energetska_klasa_num <= 3 THEN 1 ELSE 0 END)        AS klasa_c_ili_bolja,
        SUM(CASE WHEN energetska_klasa_num IS NOT NULL THEN 1 ELSE 0 END) AS ukupno_sa_poznatom_klasom,
        COUNT(*)                                                          AS ukupno_proizvoda,
        ROUND(100.0 * SUM(CASE WHEN energetska_klasa_num <= 3 THEN 1 ELSE 0 END)
                    / NULLIF(SUM(CASE WHEN energetska_klasa_num IS NOT NULL THEN 1 ELSE 0 END), 0), 2)
                                                                          AS procenat_medju_poznatima
FROM        preciscena.proizvodi;


-- ----------------------------------------------------------------------------
-- UPIT 5 i 6: Proizvodi sa cenom do 50.000 dinara, i po kategoriji
-- @naziv: Cena do 50.000 dinara
-- ----------------------------------------------------------------------------
-- U jednom redu dobijam koliko proizvoda košta najviše 50.000, koliko ih je
-- ukupno i koliki je to procenat. Granicu 50.000 sam uključila (<=).
SELECT  SUM(CASE WHEN cena_min <= 50000 THEN 1 ELSE 0 END)               AS do_50000,
        COUNT(*)                                                        AS ukupno,
        ROUND(100.0 * SUM(CASE WHEN cena_min <= 50000 THEN 1 ELSE 0 END) / COUNT(*), 2) AS procenat
FROM        preciscena.proizvodi;

-- UPIT 6 (po kategoriji uz upit 5)
-- @naziv: Cena do 50.000 po kategoriji
-- isto brojim po kategorijama sa bar 20 proizvoda, da vidim gde su jeftiniji uređaji
-- i da mala kategorija sa par artikala ne ispadne na vrhu sa 100%
SELECT  kategorija,
        SUM(CASE WHEN cena_min <= 50000 THEN 1 ELSE 0 END)               AS do_50000,
        COUNT(*)                                                        AS ukupno,
        ROUND(100.0 * SUM(CASE WHEN cena_min <= 50000 THEN 1 ELSE 0 END) / COUNT(*), 2) AS procenat
FROM        preciscena.proizvodi
GROUP BY    kategorija
HAVING      COUNT(*) >= 20
ORDER BY    procenat DESC, kategorija;


-- ----------------------------------------------------------------------------
-- UPIT 7: Top 30 televizora po najvišoj ceni
-- @naziv: Top 30 televizora po ceni
-- ----------------------------------------------------------------------------
-- ROW_NUMBER() mi daje redni broj od 1 do 30, istim redosledom kao ORDER BY.
-- Rezolucija je u dve kolone, širina i visina u pikselima, a cena_po_incu
-- pokazuje koliko je televizor skup za svoju veličinu
SELECT  ROW_NUMBER() OVER (ORDER BY cena_min DESC, naziv)               AS redni_broj,
        brend,
        naziv,
        model,
        cena_min                                                        AS cena,
        dijagonala_inch                                                 AS dijagonala,
        rezolucija_sirina_px                                            AS sirina_px,
        rezolucija_visina_px                                            AS visina_px,
        energetska_klasa,
        energetska_skala,
        cena_po_incu,
        izvori
FROM        preciscena.proizvodi
WHERE       kategorija = 'televizor'
ORDER BY    cena_min DESC, naziv
LIMIT       30;


