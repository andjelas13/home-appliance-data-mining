@echo off
setlocal

REM ===========================================================================
REM  pokreni_aplikaciju.bat - pokretanje aplikacije na racunaru bez PostgreSQL servera
REM
REM  Skripta je za racunar na kome nema PostgreSQL servera: aplikacija tada cita kopiju baze
REM  iz fajla baza\sqlite\psz_preciscena.sqlite (ili iz MySQL-a, ako se unesu podaci za njega).
REM  Trazi Python koji vec ima numpy, pandas i matplotlib i njime pokrece
REM  kod\pokreni_aplikaciju.py. Pokrece se dvoklikom ili iz korena projekta:
REM      kod\pokreni_aplikaciju.bat
REM  Ako ne nadje Python, isti .py fajl moze da se otvori u IDLE ili PyCharm-u.
REM ===========================================================================

REM prelazim u koren projekta (folder iznad kod), da putanja kod\pokreni_aplikaciju.py vazi
cd /d "%~dp0.."

REM redom probam python, py -3 i python3; prvi koji ima potrebne biblioteke pokrece moju skriptu
REM (import ide u tisini, a posle skripte skacem na kraj)
for %%P in ("python" "py -3" "python3") do (
    %%~P -c "import numpy, pandas, matplotlib" >nul 2>nul && (
        %%~P kod\pokreni_aplikaciju.py %*
        goto :kraj
    )
)

REM ako nijedan nema sve biblioteke, uzimam prvi Python koji se javi; skripta ce sama ispisati sta fali
for %%P in ("python" "py -3" "python3") do (
    %%~P --version >nul 2>nul && (
        %%~P kod\pokreni_aplikaciju.py %*
        goto :kraj
    )
)
echo [GRESKA] Python nije pronadjen. Otvori kod\pokreni_aplikaciju.py u IDLE ili PyCharm-u i pokreni ga.

REM pause sam stavila da se prozor ne zatvori pre nego sto se procitaju poruke
:kraj
pause
endlocal
