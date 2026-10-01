@echo off
setlocal

REM ===========================================================================
REM  pokreni.bat - pokretanje projekta korak po korak
REM
REM  Koraci su mi poredjani redom, jer svaki koristi ono sto je napravio prethodni.
REM  Korak preuzmi traje satima (skida stranice sa interneta), pa se pokrece
REM  jednom; ostali koraci rade nad vec snimljenim podacima i mogu da se ponove.
REM
REM  Skripta sama nalazi koren projekta (folder iznad kod), a primeri su pisani
REM  za kucanje iz korena, foldera sa kod, baza i izvestaj:  kod\pokreni.bat aplikacija
REM
REM  Za brz pregled aplikacije dovoljan je korak aplikacija (ili kod\pokreni_aplikaciju.bat):
REM  kad se PostgreSQL ne javi, aplikacija cita kopiju baze iz baza\sqlite\psz_preciscena.sqlite.
REM  Korak obnovi trazi izvezene SQL fajlove baza\primarna_baza.sql i baza\preciscena_baza.sql,
REM  koji nisu deo repozitorijuma.
REM
REM  Upotreba:
REM      pokreni.bat            - ispisuje spisak koraka
REM      pokreni.bat obnovi     - ucitava obe baze iz izvezenih SQL fajlova (moraju biti u folderu baza)
REM      pokreni.bat baza       - brise i pravi obe baze sa praznim semama (samo za rad od nule)
REM      pokreni.bat spisak     - Zadatak 1: spisak adresa iz sitemapa
REM      pokreni.bat preuzmi    - Zadatak 1: preuzimanje stranica (traje satima)
REM      pokreni.bat parsiraj   - Zadatak 1: parsiranje i punjenje primarne baze
REM      pokreni.bat ciscenje   - Zadatak 2: preciscena baza
REM      pokreni.bat upiti      - Zadatak 2: SQL upiti i izvoz u Excel
REM      pokreni.bat grafikoni  - Zadatak 3: grafikoni
REM      pokreni.bat regresija  - Zadatak 4: obucavanje modela cene i eksperimenti
REM      pokreni.bat klasteri   - Zadatak 5: klasterovanje frizidera i metoda lakta
REM      pokreni.bat preporuke  - Zadatak 6: primeri preporuka
REM      pokreni.bat provera    - poredjenje sopstvenih implementacija sa scikit-learn
REM      pokreni.bat aplikacija - prozor aplikacije (tkinter)
REM      pokreni.bat sve        - od ciscenja do provere (bez spiska, preuzimanja i parsiranja)
REM ===========================================================================

REM KOREN mi je folder iznad kod, izveden iz putanje same skripte; PY je python iz .venv
set KOREN=%~dp0..
set PY=%KOREN%\.venv\Scripts\python.exe

REM podaci za vezu sa PostgreSQL-om, isti kao u kod\zajednicko\baza.py; menjaju se promenljivim
REM okruzenja PSZ_DB_HOST, PSZ_DB_PORT, PSZ_DB_USER i PSZ_DB_PASSWORD, a PSQL je komanda klijenta
REM (postavi je pre pokretanja ako psql nije na putanji)
if not defined PSZ_DB_HOST set PSZ_DB_HOST=localhost
if not defined PSZ_DB_PORT set PSZ_DB_PORT=5433
if not defined PSZ_DB_USER set PSZ_DB_USER=psz
if not defined PSZ_DB_PASSWORD set PSZ_DB_PASSWORD=psz2026
set PGPASSWORD=%PSZ_DB_PASSWORD%
if not defined PSQL set PSQL=psql -h %PSZ_DB_HOST% -p %PSZ_DB_PORT% -U %PSZ_DB_USER%

REM bez argumenta samo ispisujem spisak koraka
if "%~1"=="" goto :pomoc
REM korake obnovi i baza radi psql (klijent PostgreSQL-a), pa za njih ne trazim virtuelno okruzenje
if /i "%~1"=="obnovi" goto :obnovi
if /i "%~1"=="baza" goto :baza

REM bez virtuelnog okruzenja ostali koraci nemaju smisla, pa ispisujem kako se pravi;
REM proveru pisem bez zagrada, jer bi zagrada iz putanje (npr. "Projekat (1)") zatvorila blok
if exist "%PY%" goto :ima_okruzenje
echo [GRESKA] Ne postoji virtuelno okruzenje: %PY%
echo          Napravi ga sa:  py -3.11 -m venv .venv
echo          pa instaliraj:  .venv\Scripts\pip install -r kod\requirements.txt
exit /b 1

:ima_okruzenje
REM korak trazim u spisku poznatih koraka; goto na nepostojecu oznaku bi prekinuo skriptu
REM sistemskom porukom, bez spiska koraka
for %%K in (spisak preuzmi parsiraj ciscenje upiti grafikoni regresija klasteri preporuke provera aplikacija sve) do if /i "%~1"=="%%K" goto :%%K
goto :nepoznato

REM ---------------------------------------------------------------------------
:baza
REM Brisem i ponovo pravim dve odvojene baze, psz_primarna (Zadatak 1) i psz_preciscena
REM (Zadatak 2 trazi novu, revidiranu bazu), pa u svaku ucitavam njenu praznu semu.
echo [KORAK] Pravim dve prazne baze i njihove seme...
%PSQL% -d postgres -q -c "DROP DATABASE IF EXISTS psz_primarna;" -c "DROP DATABASE IF EXISTS psz_preciscena;" -c "CREATE DATABASE psz_primarna;" -c "CREATE DATABASE psz_preciscena;"
%PSQL% -d psz_primarna -q < "%KOREN%\baza\01_sema_primarna.sql"
%PSQL% -d psz_preciscena -q < "%KOREN%\baza\02_sema_preciscena.sql"
goto :kraj

:obnovi
REM Brisem obe baze i punim ih iz baza\primarna_baza.sql i baza\preciscena_baza.sql.
REM Korak trazi ta dva izvezena SQL fajla u folderu baza. Oni nisu deo repozitorijuma, kao
REM ni preuzete HTML stranice (preko 2,5 GB), pa se bez njih primarna baza ne moze ni ucitati
REM ni napraviti ponovnim parsiranjem. Za brz pregled aplikacije sluzi korak aplikacija ili
REM kod\pokreni_aplikaciju.bat.
echo [KORAK] Ucitavam primarnu i preciscenu bazu iz foldera baza...
%PSQL% -d postgres -q -c "DROP DATABASE IF EXISTS psz_primarna;" -c "DROP DATABASE IF EXISTS psz_preciscena;" -c "CREATE DATABASE psz_primarna;" -c "CREATE DATABASE psz_preciscena;"
REM ON_ERROR_STOP=1 zaustavlja psql na prvoj SQL gresci, pa errorlevel javi neuspeh;
REM -1 ucitava fajl u jednoj transakciji, pa redovi u tabelama ostaju istim redom
REM kao u fajlu (od tog redosleda zavisi podela na trening i test)
%PSQL% -d psz_primarna -q -1 -v ON_ERROR_STOP=1 < "%KOREN%\baza\primarna_baza.sql"
if errorlevel 1 ( echo [GRESKA] Ucitavanje primarne baze nije uspelo. & exit /b 1 )
%PSQL% -d psz_preciscena -q -1 -v ON_ERROR_STOP=1 < "%KOREN%\baza\preciscena_baza.sql"
if errorlevel 1 ( echo [GRESKA] Ucitavanje preciscene baze nije uspelo. & exit /b 1 )
REM na kraju ispisujem broj proizvoda u obe baze, kao brzu proveru ucitavanja
%PSQL% -d psz_primarna -t -c "SELECT 'psz_primarna:   ' || COUNT(*) || ' proizvoda' FROM primarna.proizvodi;"
%PSQL% -d psz_preciscena -t -c "SELECT 'psz_preciscena: ' || COUNT(*) || ' proizvoda' FROM preciscena.proizvodi;"
goto :kraj

:spisak
REM indekser prvo cita sitemap svake prodavnice i pravi spisak adresa proizvoda
echo [KORAK] Zadatak 1 - pravim spisak adresa iz sitemapa...
cd /d "%KOREN%\kod\indekser"
"%PY%" indekser.py --faza spisak --prodavnica winwin
"%PY%" indekser.py --faza spisak --prodavnica gigatron
goto :kraj

:preuzmi
REM preuzimanje sam odvojila od parsiranja: stranice snimim na disk, pa parser radi bez
REM novih zahteva; moj indekser postuje robots.txt, pravi pauze i radi sa najvise 5 radnika
echo [KORAK] Zadatak 1 - preuzimam stranice. OVO TRAJE VISE SATI.
cd /d "%KOREN%\kod\indekser"
"%PY%" indekser.py --faza preuzmi --prodavnica winwin
"%PY%" indekser.py --faza preuzmi --prodavnica gigatron
goto :kraj

:parsiraj
REM parser cita snimljene stranice jedne pa druge prodavnice i upisuje ih u primarnu bazu
echo [KORAK] Zadatak 1 - parsiram stranice i punim primarnu bazu...
cd /d "%KOREN%\kod\parser"
"%PY%" upis_u_bazu.py --prodavnica winwin
"%PY%" upis_u_bazu.py --prodavnica gigatron
goto :kraj

:ciscenje
REM ciscenje.py cita primarnu bazu, spaja iste uredjaje i puni preciscenu bazu
echo [KORAK] Zadatak 2 - preprocesiranje i preciscena baza...
cd /d "%KOREN%\kod\preprocessing"
"%PY%" ciscenje.py
goto :kraj

:upiti
REM izvoz_rezultata.py pokrece moje SQL upite i rezultate izvozi u Excel
echo [KORAK] Zadatak 2 - SQL upiti i izvoz rezultata...
cd /d "%KOREN%\kod\analiza"
"%PY%" izvoz_rezultata.py
goto :kraj

:grafikoni
REM grafikone za Zadatak 3 crtam iz preciscene baze
echo [KORAK] Zadatak 3 - generisem grafikone...
cd /d "%KOREN%\kod\vizuelizacija"
"%PY%" grafikoni.py
goto :kraj

:regresija
REM prvo obucavam model sa 25000 iteracija gradijentnog spusta, pa pokrecem eksperimente
REM (ukupno oko 4 minuta)
echo [KORAK] Zadatak 4 - obucavam model za predvidjanje cene...
cd /d "%KOREN%\kod\models"
"%PY%" regresija.py --iteracije 25000
"%PY%" regresija.py --eksperimenti
goto :kraj

:klasteri
REM frizidere delim na 4 klastera po ceni, zapremini i energetskom rangu (tezine 50, 30, 20),
REM a drugi poziv sa --lakat crta grafikon za izbor broja klastera
echo [KORAK] Zadatak 5 - klasterovanje...
cd /d "%KOREN%\kod\models"
"%PY%" kmeans.py --kategorija frizider --k 4 --obelezja cena_min,zapremina_l,energetska_rang --tezine 50,30,20
"%PY%" kmeans.py --kategorija frizider --obelezja cena_min,zapremina_l,energetska_rang --tezine 50,30,20 --lakat
goto :kraj

:preporuke
REM preporuke.py ispisuje primere preporuka i snima ih u preporuke_primeri.txt
echo [KORAK] Zadatak 6 - primeri preporuka...
cd /d "%KOREN%\kod\models"
"%PY%" preporuke.py --primeri
goto :kraj

:provera
REM verifikacija.py poredi moje rucno napisane modele sa gotovim iz scikit-learn
echo [KORAK] Verifikacija sopstvenih implementacija (scikit-learn)...
cd /d "%KOREN%\kod\evaluation"
"%PY%" verifikacija.py
goto :kraj

:aplikacija
REM app.py pokrecem iz njegovog foldera; otvara se prozor aplikacije
echo [KORAK] Pokrecem aplikaciju (prozor)
cd /d "%KOREN%\kod\app"
"%PY%" app.py
goto :kraj

:sve
REM call mi pokrece ovaj isti fajl za svaki korak i vraca se ovde; bez call bi se
REM skripta zavrsila posle prvog koraka
call "%~f0" ciscenje
call "%~f0" upiti
call "%~f0" grafikoni
call "%~f0" regresija
call "%~f0" klasteri
call "%~f0" preporuke
call "%~f0" provera
echo.
echo [OK] Sve je gotovo. Rezultati su u folderu sa izvestajem.
goto :kraj

REM ---------------------------------------------------------------------------
:nepoznato
REM posle poruke o gresci namerno nema goto, pa se nastavlja u :pomoc i ispisuje spisak koraka
echo [GRESKA] Nepoznat korak: %~1
:pomoc
echo.
echo   Brz pregled aplikacije:  aplikacija  (ili kod\pokreni_aplikaciju.bat)
echo   Korak obnovi trazi fajlove primarna_baza.sql i preciscena_baza.sql u folderu baza;
echo   posle njega korak sve ponovo pravi sve rezultate.
echo.
echo   Koraci:  obnovi ^| baza ^| spisak ^| preuzmi ^| parsiraj ^| ciscenje ^| upiti
echo            grafikoni ^| regresija ^| klasteri ^| preporuke ^| provera
echo            aplikacija ^| sve
echo.
echo   Primer:  kod\pokreni.bat aplikacija
echo.

REM svi koraci zavrsavaju ovde; endlocal vraca promenljive kakve su bile
:kraj
endlocal
