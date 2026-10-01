-- ============================================================================
-- 01_sema_primarna.sql — Šema PRIMARNE baze podataka (Zadatak 1)
--
-- Opis:
--   Primarna baza čuva sirove zapise onako kako ih je parser pročitao sa
--   sajtova, bez čišćenja i sa nepotpunim zapisima. Tako u Zadatku 2 mogu da
--   izmerim koliko je zapisa odbačeno i zašto.
--
-- Izvori:
--   winwin.rs i gigatron.rs
--
-- Napomena o modelu podataka:
--   Svaka vrsta uređaja ima svoje karakteristike (televizor dijagonalu,
--   frižider zapreminu, veš mašina kapacitet), pa bi fiksne kolone dale tabelu
--   sa mnogo praznih polja. Zato su karakteristike u tabeli karakteristike kao
--   parovi atribut–vrednost, a u kolone se prevode tek u Zadatku 2.
--
-- Pokretanje:
--   psql -h localhost -p 5433 -U psz -d psz_primarna -f baza/01_sema_primarna.sql
-- ============================================================================

DROP SCHEMA IF EXISTS primarna CASCADE;
CREATE SCHEMA primarna;

-- ----------------------------------------------------------------------------
-- Šifarnik prodavnica (izvora podataka), sa dva unapred upisana reda
-- ----------------------------------------------------------------------------
CREATE TABLE primarna.prodavnice (
    id              SERIAL PRIMARY KEY,
    sifra           TEXT NOT NULL UNIQUE,   -- 'winwin' ili 'gigatron'
    naziv           TEXT NOT NULL,
    osnovni_url     TEXT NOT NULL,
    platforma       TEXT,                   -- 'Magento' ili 'Next.js', od toga zavisi parser
    tehnika_parsiranja TEXT                 -- npr. 'DOM tabela (th/td)'
);

INSERT INTO primarna.prodavnice (sifra, naziv, osnovni_url, platforma, tehnika_parsiranja) VALUES
    ('winwin',      'Win Win',      'https://www.winwin.rs',      'Magento', 'DOM tabela (th/td)'),
    ('gigatron',    'Gigatron',     'https://gigatron.rs',        'Next.js', 'JSON-LD (schema.org) + DOM tabela');

-- ----------------------------------------------------------------------------
-- Sirovi zapisi o proizvodima (jedan red = jedna stranica proizvoda)
-- ----------------------------------------------------------------------------
CREATE TABLE primarna.proizvodi (
    id                  SERIAL PRIMARY KEY,
    prodavnica_id       INTEGER NOT NULL REFERENCES primarna.prodavnice(id),
    url                 TEXT NOT NULL,
    sku                 TEXT,               -- šifra artikla u prodavnici
    naziv               TEXT,
    brend               TEXT,
    kategorija_puna     TEXT,               -- cela putanja kategorija, npr. 'Bela tehnika/Frižideri/...'
    kategorija          TEXT,               -- poslednji nivo putanje, npr. 'Kombinovani frižideri'
    cena                NUMERIC(12,2),      -- NULL ako cena nije prikazana (npr. 'nije u ponudi')
    valuta              TEXT DEFAULT 'RSD',
    dostupnost          TEXT,               -- sirova oznaka sa sajta ('Dostupno odmah', 'InStock')
    na_stanju           BOOLEAN,            -- dostupnost prevedena u da/ne, NULL ako se ne zna
    ocena               NUMERIC(3,2),       -- prosečna ocena kupaca, ako postoji (samo Gigatron)
    broj_ocena          INTEGER,
    opis                TEXT,
    datum_preuzimanja   TIMESTAMPTZ NOT NULL DEFAULT now(),  -- posle upisa ga prepisujem vremenom iz dnevnik_indeksiranja

    -- ista adresa u istoj prodavnici može da postoji samo jednom
    CONSTRAINT uq_proizvod_url UNIQUE (prodavnica_id, url)
);

-- indeksi za kolone po kojima se najčešće filtrira i grupiše
CREATE INDEX ix_proizvodi_prodavnica  ON primarna.proizvodi (prodavnica_id);
CREATE INDEX ix_proizvodi_kategorija  ON primarna.proizvodi (kategorija);
CREATE INDEX ix_proizvodi_brend       ON primarna.proizvodi (brend);
CREATE INDEX ix_proizvodi_cena        ON primarna.proizvodi (cena);

-- ----------------------------------------------------------------------------
-- Tehničke karakteristike (atribut – vrednost)
--   Jedan red je jedna stavka iz specifikacije na stranici proizvoda. Vrednost
--   ostaje tekst kao na sajtu ('307 l', 'A+ (po prethodnoj klasifikaciji)'),
--   a broj iz nje vadi se u Zadatku 2. Brisanjem proizvoda brišu se i njegovi redovi.
-- ----------------------------------------------------------------------------
CREATE TABLE primarna.karakteristike (
    id              SERIAL PRIMARY KEY,
    proizvod_id     INTEGER NOT NULL REFERENCES primarna.proizvodi(id) ON DELETE CASCADE,
    naziv           TEXT NOT NULL,          -- 'Energetska klasa', 'Zapremina frižidera', ...
    vrednost        TEXT                    -- '307 l', 'A+', 'NoFrost Plus', ...
);

CREATE INDEX ix_karakteristike_proizvod ON primarna.karakteristike (proizvod_id);
CREATE INDEX ix_karakteristike_naziv    ON primarna.karakteristike (naziv);

-- ----------------------------------------------------------------------------
-- Dnevnik indeksiranja
--   Za svaku adresu sa spiska indekser upisuje HTTP status, uspeh, poruku
--   greške i trajanje u ms. U izveštaju se odavde broje zahtevi i neuspesi, a iz
--   kolone vreme čita se period preuzimanja.
-- ----------------------------------------------------------------------------
CREATE TABLE primarna.dnevnik_indeksiranja (
    id              SERIAL PRIMARY KEY,
    prodavnica_id   INTEGER REFERENCES primarna.prodavnice(id),
    url             TEXT NOT NULL,
    http_status     INTEGER,
    uspesno         BOOLEAN NOT NULL,
    poruka_greske   TEXT,
    trajanje_ms     INTEGER,
    vreme           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_dnevnik_vreme   ON primarna.dnevnik_indeksiranja (vreme);
CREATE INDEX ix_dnevnik_uspesno ON primarna.dnevnik_indeksiranja (uspesno);

-- ----------------------------------------------------------------------------
-- Pomoćni pogled: po prodavnici broj proizvoda, sa cenom, brendova, kategorija
-- i vreme prvog i poslednjeg preuzimanja
-- ----------------------------------------------------------------------------
CREATE VIEW primarna.v_pregled AS
SELECT  pr.sifra                                    AS prodavnica,
        COUNT(*)                                    AS broj_proizvoda,
        COUNT(p.cena)                               AS sa_cenom,
        COUNT(DISTINCT p.brend)                     AS broj_brendova,
        COUNT(DISTINCT p.kategorija)                AS broj_kategorija,
        MIN(p.datum_preuzimanja)                    AS prvo_preuzimanje,
        MAX(p.datum_preuzimanja)                    AS poslednje_preuzimanje
FROM        primarna.proizvodi  p
JOIN        primarna.prodavnice pr ON pr.id = p.prodavnica_id
GROUP BY    pr.sifra
ORDER BY    broj_proizvoda DESC;
