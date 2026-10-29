@echo off
chcp 65001 >nul
title Installer JARVIS comme application
cd /d "%~dp0"

echo.
echo   Installation de JARVIS comme application Windows
echo   ─────────────────────────────────────────────────
echo.
echo   Cela installe un composant gratuit (pywebview) qui permet
echo   d'ouvrir JARVIS dans sa propre fenetre, sans navigateur.
echo.
echo   Une seule fois. Cela prend une minute.
echo.
pause

echo.
echo   Installation en cours...
echo.

py -3 -m pip install --user --upgrade pywebview
if errorlevel 1 goto essai2
goto fin

:essai2
python -m pip install --user --upgrade pywebview
if errorlevel 1 goto essai3
goto fin

:essai3
python3 -m pip install --user --upgrade pywebview
if errorlevel 1 goto echec
goto fin

:echec
echo.
echo   L'installation n'a pas pu se faire.
echo.
echo   Ce n'est pas grave : JARVIS fonctionne quand meme, il s'ouvrira
echo   simplement dans votre navigateur. Double-cliquez sur
echo   LANCER-JARVIS.bat et tout marchera.
echo.
pause
exit /b 1

:fin
echo.
echo   C'est installe.
echo.
echo   Desormais, double-cliquez sur LANCER-JARVIS.bat : JARVIS s'ouvrira
echo   dans sa propre fenetre, avec son icone dans la barre des taches.
echo.
pause
