#!/bin/bash
# JARVIS — lancement sur Mac et Linux. Double-clic (Mac) ou ./Lancer-JARVIS.command
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1; then
    exec python3 lancer_jarvis.py
fi

echo ""
echo "  Python 3 n'est pas installé sur cet ordinateur."
echo ""
echo "  Sur Mac : ouvrez le Terminal et tapez"
echo "      xcode-select --install"
echo "  puis relancez ce fichier."
echo ""
read -r -p "  Appuyez sur Entrée pour fermer."
