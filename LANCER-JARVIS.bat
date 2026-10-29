@echo off
chcp 65001 >nul
title JARVIS
cd /d "%~dp0"

echo.
echo   JARVIS - demarrage...
echo.

rem Essaie les trois façons d'appeler Python sous Windows.
py -3 lancer_jarvis.py
if errorlevel 9009 goto essai2
goto fin

:essai2
python lancer_jarvis.py
if errorlevel 9009 goto essai3
goto fin

:essai3
python3 lancer_jarvis.py
if errorlevel 9009 goto pasPython
goto fin

:pasPython
echo.
echo   Python n'est pas installe sur cet ordinateur.
echo.
echo   1. Ouvrez https://www.python.org/downloads/
echo   2. Cliquez le gros bouton jaune "Download Python"
echo   3. Lancez le fichier telecharge
echo   4. IMPORTANT : cochez "Add python.exe to PATH" sur le premier ecran
echo   5. Cliquez "Install Now", puis revenez ici et relancez ce fichier
echo.

:fin
echo.
pause
