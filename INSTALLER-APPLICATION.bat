@echo off
chcp 65001 >nul
title JARVIS - installation comme application
cd /d "%~dp0"

echo.
echo   Installation de JARVIS comme application Windows
echo   ------------------------------------------------
echo.
echo   Ceci va :
echo     - installer un composant gratuit (pywebview) si besoin
echo     - creer une icone JARVIS sur votre Bureau
echo.
echo   Une seule fois. Cela prend une minute.
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\installer.ps1"
