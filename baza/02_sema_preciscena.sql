-- ============================================================================
-- 02_sema_preciscena.sql — Šema PREČIŠĆENE baze podataka (Zadatak 2)
--
-- Opis:
--   Prečišćenu bazu puni skripta ciscenje.py iz primarne baze. U njoj je jedan
--   red po uređaju (zapisi iz obe prodavnice spojeni), kategorije su svedene na
--   kontrolisani rečnik, karakteristike su numeričke kolone, a dodati su i
--   izvedeni pokazatelji (cena po inču, litru, kilogramu i kW).
--
-- Zašto se karakteristike prevode u kolone:
--   Modeli iz zadataka 4, 5 i 6 traže brojeve u kolonama, a u primarnoj bazi je
--   karakteristika tekst u redu ('Zapremina' = '204 l'). Prevođenje spaja
--   sinonime, vadi broj iz teksta ('121,5 cm' → 121.5) i proverava opseg.
--
-- Napomena o energetskoj klasi:
--   Stara skala (klase sa plusevima i slova od A nadole) i nova (A do G) se ne
--   mogu porediti, a zvanično preslikavanje iz jedne u drugu ne postoji. Zato
--   čuvam klasu i skalu odvojeno, a rang (1 = najbolja) računam samo unutar
--   svoje skale. Skalu ciscenje.py određuje po oznaci u tekstu ('Novo',
--   'po prethodnoj klasifikaciji') ili po vrsti uređaja.
--
-- Pokretanje:
--   psql -h localhost -p 5433 -U psz -d psz_preciscena -f baza/02_sema_preciscena.sql
-- ============================================================================

DROP SCHEMA IF EXISTS preciscena CASCADE;
CREATE SCHEMA preciscena;

-- ----------------------------------------------------------------------------
-- Prečišćeni proizvodi
-- ----------------------------------------------------------------------------
CREATE TABLE preciscena.proizvodi (
    id                      SERIAL PRIMARY KEY,

    -- --- identitet ---
    brend                   TEXT NOT NULL,
    model                   TEXT,                   -- iz karakteristike 'Model', a ako je nema iz naziva
    naziv                   TEXT NOT NULL,
    kljuc_spajanja          TEXT NOT NULL,          -- 'brend|model' (ili 'brend|naziv'), po njemu se spajaju zapisi

    -- --- kategorija ---
    kategorija              TEXT NOT NULL,          -- kontrolisani rečnik: 'televizor', 'frizider', ...
    kategorija_izvorna      TEXT,                   -- kako je pisalo na sajtu
    grupa                   TEXT,                   -- 'tv', 'bela tehnika', 'klimatizacija' ili 'mali aparati'

    -- --- cena i prodavnice ---
    cena_min                NUMERIC(12,2),
    cena_max                NUMERIC(12,2),
    cena_prosek             NUMERIC(12,2),
    razlika_cene_procenat   NUMERIC(6,2),           -- (max-min)/min*100 između svih oglasa, i unutar iste prodavnice
    broj_prodavnica         SMALLINT NOT NULL DEFAULT 1,
    izvori                  TEXT NOT NULL,          -- šifre prodavnica abecedno, npr. 'gigatron,winwin'
    na_stanju               BOOLEAN,                -- TRUE ako je na stanju bar u jednoj prodavnici; NULL kad se ne zna
    ocena                   NUMERIC(3,2),
    broj_ocena              INTEGER,

    -- --- energetska klasa ---
    energetska_klasa        TEXT,                   -- 'A', 'A+', 'F', ...
    energetska_skala        TEXT,                   -- 'nova' (A–G) ili 'stara' (A+++ i niže)
    energetska_klasa_num    SMALLINT,               -- rang unutar svoje skale, 1 = najbolja

    -- --- tehničke karakteristike (NULL ako izvor nema podatak) ---
    dijagonala_inch         NUMERIC(6,2),
    rezolucija_sirina_px    INTEGER,
    rezolucija_visina_px    INTEGER,
    zapremina_l             NUMERIC(8,2),           -- ukupna zapremina uređaja, a kod usisivača kese i kod friteze posude
    zapremina_frizider_l    NUMERIC(8,2),
    zapremina_zamrzivac_l   NUMERIC(8,2),
    kapacitet_pranja_kg     NUMERIC(6,2),
    kapacitet_kompleta      SMALLINT,               -- mašine za sudove
    brzina_centrifuge       INTEGER,
    snaga_w                 NUMERIC(10,2),          -- električna snaga uređaja
    kapacitet_hladjenja_btu INTEGER,                -- klima uređaji
    kapacitet_hladjenja_kw  NUMERIC(6,2),
    visina_cm               NUMERIC(7,2),
    sirina_cm               NUMERIC(7,2),
    dubina_cm               NUMERIC(7,2),
    tezina_kg               NUMERIC(7,2),
    nivo_buke_db            NUMERIC(5,1),
    potrosnja_kwh           NUMERIC(8,3),
    broj_programa           SMALLINT,
    broj_brzina             SMALLINT,
    -- gabarit = proizvod tri spoljne dimenzije u cm³; računa se i iz zapisa
    -- '17,2 cm x 7 cm x 16 cm' bez oznake koja je dimenzija koja, jer proizvod
    -- ne zavisi od redosleda
    gabarit_cm3             NUMERIC(14,2),

    -- --- izvedeni pokazatelji ---
    -- cena_min podeljena veličinom uređaja; televizor od 100.000 dinara nije
    -- skup ako ima 75 inča, a jeste ako ima 32
    cena_po_incu            NUMERIC(12,2),
    cena_po_litru           NUMERIC(12,2),
    cena_po_kg_kapaciteta   NUMERIC(12,2),
    cena_po_kw_hladjenja    NUMERIC(12,2),

    -- --- kontrola kvaliteta ---
    broj_karakteristika     SMALLINT NOT NULL DEFAULT 0,   -- popunjena tehnička polja, bez energetske klase i polja izvedenih iz drugih
    datum_obrade            TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- isti ključ sme da postoji u različitim kategorijama, ali u jednoj samo jednom
    CONSTRAINT uq_kljuc_spajanja UNIQUE (kljuc_spajanja, kategorija)
);

CREATE INDEX ix_pr_kategorija  ON preciscena.proizvodi (kategorija);
CREATE INDEX ix_pr_brend       ON preciscena.proizvodi (brend);
CREATE INDEX ix_pr_cena        ON preciscena.proizvodi (cena_min);
CREATE INDEX ix_pr_energetska  ON preciscena.proizvodi (energetska_klasa);

-- ----------------------------------------------------------------------------
-- Veza prečišćenog proizvoda sa zapisima iz kojih je nastao
--   Za svaki spojeni zapis čuva id iz primarne baze, prodavnicu, adresu i cenu,
--   pa se za svaki red vidi odakle je došao i koliko je koštao u kojoj prodavnici.
-- ----------------------------------------------------------------------------
CREATE TABLE preciscena.poreklo (
    id                  SERIAL PRIMARY KEY,
    preciscen_id        INTEGER NOT NULL REFERENCES preciscena.proizvodi(id) ON DELETE CASCADE,
    primarni_id         INTEGER NOT NULL,
    prodavnica          TEXT NOT NULL,
    url                 TEXT NOT NULL,
    cena                NUMERIC(12,2)
);

CREATE INDEX ix_poreklo_preciscen ON preciscena.poreklo (preciscen_id);
CREATE INDEX ix_poreklo_prodavnica ON preciscena.poreklo (prodavnica);

-- ----------------------------------------------------------------------------
-- Dnevnik čišćenja
--   Jedan red po koraku čišćenja: koliko je zapisa učitano, odbačeno iz kog
--   razloga, spojeno kao duplikat i upisano. Iz njega izveštaj objašnjava
--   zašto je u prečišćenoj bazi manje redova nego u primarnoj.
-- ----------------------------------------------------------------------------
CREATE TABLE preciscena.dnevnik_ciscenja (
    id              SERIAL PRIMARY KEY,
    korak           TEXT NOT NULL,          -- npr. 'odbačeno: cena van opsega', 'spojenih zapisa u duplikate'
    broj_zapisa     INTEGER NOT NULL,
    vreme           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- Pogled: poređenje cena istog proizvoda po prodavnicama
--   Isti uređaj ponekad ima dva oglasa u istoj prodavnici, pa se za svaku
--   prodavnicu uzima njena najniža cena (iz tabele poreklo), a razlika se
--   računa između prodavnica: (viša − niža) / niža · 100. Samo proizvodi koji
--   postoje u obe prodavnice, od najveće razlike naniže.
-- ----------------------------------------------------------------------------
CREATE VIEW preciscena.v_poredjenje_cena AS
WITH po_prodavnici AS (
    SELECT  preciscen_id, prodavnica, MIN(cena) AS cena
    FROM    preciscena.poreklo
    WHERE   cena IS NOT NULL
    GROUP BY 1, 2
), raspon AS (
    SELECT  preciscen_id, MIN(cena) AS niza_cena, MAX(cena) AS visa_cena
    FROM    po_prodavnici
    GROUP BY 1
    HAVING  COUNT(*) > 1
)
SELECT  p.id,
        p.brend,
        p.naziv,
        p.kategorija,
        r.niza_cena,
        r.visa_cena,
        r.visa_cena - r.niza_cena                                   AS razlika_dinara,
        ROUND((r.visa_cena - r.niza_cena) / r.niza_cena * 100, 2)   AS razlika_procenat,
        p.izvori
FROM        raspon r
JOIN        preciscena.proizvodi p ON p.id = r.preciscen_id
ORDER BY    razlika_procenat DESC;

-- ----------------------------------------------------------------------------
-- Pogled: popunjenost kolona po kategoriji
--   COUNT(kolona) broji samo vrednosti koje nisu NULL, pa odnos sa COUNT(*)
--   daje procenat proizvoda kojima je ta karakteristika poznata
-- ----------------------------------------------------------------------------
CREATE VIEW preciscena.v_popunjenost AS
SELECT  kategorija,
        COUNT(*)                                                        AS ukupno,
        ROUND(100.0 * COUNT(cena_min)              / COUNT(*), 1)       AS cena_pct,
        ROUND(100.0 * COUNT(energetska_klasa)      / COUNT(*), 1)       AS energetska_pct,
        ROUND(100.0 * COUNT(dijagonala_inch)       / COUNT(*), 1)       AS dijagonala_pct,
        ROUND(100.0 * COUNT(zapremina_l)           / COUNT(*), 1)       AS zapremina_pct,
        ROUND(100.0 * COUNT(kapacitet_pranja_kg)   / COUNT(*), 1)       AS kapacitet_pct,
        ROUND(100.0 * COUNT(snaga_w)               / COUNT(*), 1)       AS snaga_pct,
        ROUND(AVG(broj_karakteristika), 1)                              AS prosek_popunjenih
FROM        preciscena.proizvodi
GROUP BY    kategorija
ORDER BY    ukupno DESC, kategorija;
