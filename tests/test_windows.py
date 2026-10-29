#!/usr/bin/env python3
"""Détails Windows qui cassent une installation sans qu'on comprenne pourquoi.

Aucun de ces contrôles ne peut être fait en lançant Windows ici : ils portent sur
les fichiers livrés. Ce sont les pièges classiques :

1. un .bat avec des fins de ligne Unix (labels et goto se comportent mal) ;
2. un .bat ou un .ps1 avec des accents (cmd et PowerShell les abîment) ;
3. une icône .ico absente ou sans les bonnes tailles (raccourci sans image) ;
4. un fichier annoncé dans la documentation mais oublié dans l'archive.

Usage : python3 tests/test_windows.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTATS: list[tuple[bool, str, str]] = []


def verifier(label: str, ok: bool, detail: str = "") -> None:
    RESULTATS.append((ok, label, detail))
    print(f"{'OK  ' if ok else 'ÉCHEC'} {label:<50} {detail}")


def sans_accent(chemin: Path) -> tuple[bool, str]:
    donnees = chemin.read_bytes()
    mauvais = [i for i, octet in enumerate(donnees) if octet > 127]
    return (not mauvais, f"{len(mauvais)} octet(s)" if mauvais else "")


def fichiers_bat() -> list[Path]:
    return sorted(ROOT.glob("*.bat"))


def main() -> int:
    bat = fichiers_bat()
    verifier("des fichiers .bat sont livrés", len(bat) >= 2, f"{len(bat)}")

    for chemin in bat:
        donnees = chemin.read_bytes()
        crlf = donnees.count(b"\r\n")
        lf = donnees.count(b"\n")
        verifier(f"{chemin.name} : fins de ligne Windows", crlf == lf and crlf > 0,
                 f"{crlf} CRLF / {lf} LF")
        propre, detail = sans_accent(chemin)
        verifier(f"{chemin.name} : sans accents", propre, detail)

    ps1 = ROOT / "windows" / "installer.ps1"
    verifier("le script d'installation Windows existe", ps1.is_file())
    if ps1.is_file():
        propre, detail = sans_accent(ps1)
        verifier("installer.ps1 : sans accents", propre, detail)
        texte = ps1.read_text(encoding="utf-8")
        verifier("installer.ps1 : accolades equilibrees",
                 texte.count("{") == texte.count("}"), f"{texte.count('{')} / {texte.count('}')}")
        verifier("installer.ps1 : cree un raccourci Bureau", "Desktop" in texte)
        verifier("installer.ps1 : cree un raccourci menu Demarrer", "StartMenu" in texte)
        verifier("installer.ps1 : utilise pythonw (sans console)", "pythonw" in texte)

    icone = ROOT / "windows" / "jarvis.ico"
    verifier("l'icone Windows existe", icone.is_file())
    if icone.is_file():
        entete = icone.read_bytes()[:4]
        verifier("l'icone est un vrai fichier .ico",
                 entete[:2] == b"\x00\x00" and entete[2:4] == b"\x01\x00", repr(entete))
        # Lecture directe de l'en-tête ICO : aucune bibliothèque nécessaire.
        # 6 octets d'en-tête, puis 16 octets par image (largeur, hauteur, ...).
        brut = icone.read_bytes()
        nombre = int.from_bytes(brut[4:6], "little")
        tailles = []
        for index in range(nombre):
            debut = 6 + index * 16
            largeur = brut[debut] or 256   # 0 signifie 256 dans le format ICO
            hauteur = brut[debut + 1] or 256
            tailles.append((largeur, hauteur))
        tailles = sorted(tailles)
        verifier("l'icone contient plusieurs tailles", nombre >= 5, str(tailles))
        verifier("l'icone contient 256x256", (256, 256) in tailles, str(tailles))

    # Le lanceur doit savoir retrouver l'icone et la transmettre.
    lanceur = (ROOT / "lancer_jarvis.py").read_text(encoding="utf-8")
    verifier("le lanceur cherche l'icone", "jarvis.ico" in lanceur)
    verifier("le lanceur la transmet a la fenetre", 'options["image"]' in lanceur)

    # La documentation ne doit annoncer que des fichiers réellement livrés.
    doc = ROOT / "DEMARRER-EN-LOCAL.md"
    verifier("la documentation existe", doc.is_file())
    if doc.is_file():
        texte = doc.read_text(encoding="utf-8")
        annonces = set(re.findall(r"`([A-Za-z0-9_\-]+\.(?:bat|command|md|py))`", texte))
        manquants = [nom for nom in annonces if not (ROOT / nom).is_file()
                     and not (ROOT / "windows" / nom).is_file()]
        verifier("les fichiers annonces existent tous", not manquants, str(manquants))
        verifier("la doc mentionne le raccourci du Bureau", "Bureau" in texte)
        verifier("la doc explique la voix", "voix naturelle" in texte)

    # L'installation doit proposer la voix naturelle, sans jamais y obliger.
    installateur = (ROOT / "windows" / "installer.ps1").read_text(encoding="utf-8")
    verifier("l'installation propose la voix naturelle", "edge-tts" in installateur)
    verifier("la voix naturelle reste facultative",
             "pas grave" in installateur and "voix de Windows" in installateur)

    reussites = sum(1 for ok, _, _ in RESULTATS if ok)
    print(f"\n{reussites}/{len(RESULTATS)} vérifications passées")
    return 0 if reussites == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
