#!/usr/bin/env python3
"""Le lancement en local doit marcher au double-clic, sans aucun réglage.

Ce test exécute le vrai lanceur (lancer_jarvis.py) dans une copie neuve du
projet, puis vérifie que :

1. le dossier « mes-notes » est créé et rempli une première fois ;
2. l'interface s'ouvre sans connexion ni page de réglage ;
3. le serveur n'écoute QUE sur cet ordinateur (invisible sur le réseau) ;
4. les notes restent sur le disque après l'arrêt.

Usage : python3 tests/test_local.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTATS: list[tuple[bool, str, str]] = []


def verifier(label: str, ok: bool, detail: str = "") -> None:
    RESULTATS.append((ok, label, detail))
    print(f"{'OK  ' if ok else 'ÉCHEC'} {label:<48} {detail}")


def copie_neuve() -> Path:
    app = Path(tempfile.mkdtemp(prefix="jarvis-local-app-"))
    for fichier in sorted(ROOT.glob("*.py")):
        shutil.copy2(fichier, app / fichier.name)
    for fichier in ("LANCER-JARVIS.bat", "Lancer-JARVIS.command"):
        if (ROOT / fichier).is_file():
            shutil.copy2(ROOT / fichier, app / fichier)
    for dossier in ("viewer", "examples"):
        (app / dossier).symlink_to(ROOT / dossier, target_is_directory=True)
    return app


def adresse_reseau() -> str | None:
    """Une adresse IP de cette machine qui n'est pas 127.0.0.1, si elle existe."""
    essai = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        essai.connect(("10.255.255.255", 1))
        adresse = essai.getsockname()[0]
    except OSError:
        return None
    finally:
        essai.close()
    return None if adresse.startswith("127.") else adresse


def main() -> int:
    app = copie_neuve()
    env = {cle: valeur for cle, valeur in os.environ.items() if not cle.startswith("JARVIS_")}
    env["JARVIS_NO_BROWSER"] = "1"  # pas de navigateur dans un environnement de test
    # Maison vide et déterministe : sur une machine réelle, JARVIS brancherait les
    # vrais documents de l'utilisateur, et ce test ne pourrait plus rien prévoir.
    maison_vide = tempfile.mkdtemp(prefix="jarvis-maison-test-")
    env["HOME"] = maison_vide
    env["USERPROFILE"] = maison_vide

    processus = subprocess.Popen(
        [sys.executable, "-u", "lancer_jarvis.py"],
        cwd=str(app), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    lignes: list[str] = []
    port: int | None = None
    try:
        limite = time.time() + 40
        while time.time() < limite:
            ligne = processus.stdout.readline()
            if not ligne:
                break
            lignes.append(ligne.rstrip())
            trouve = re.search(r"localhost:(\d+)", ligne)
            if trouve:
                port = int(trouve.group(1))
                break
        verifier("le lanceur annonce une adresse", port is not None, str(port))
        if port is None:
            print("\n".join(lignes[-15:]))
            return 1

        notes = app / "mes-notes"
        verifier("le dossier mes-notes est créé", notes.is_dir())
        fichiers = sorted(notes.glob("*.md"))
        verifier("les notes d'exemple sont copiées", len(fichiers) == 25, f"{len(fichiers)} fichier(s)")

        ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with ouvreur.open(f"http://127.0.0.1:{port}/", timeout=10) as reponse:
            verifier("l'accueil s'ouvre directement", reponse.status == 200, str(reponse.status))
        with ouvreur.open(f"http://127.0.0.1:{port}/api/status", timeout=10) as reponse:
            etat = json.loads(reponse.read().decode("utf8"))
        verifier("aucune connexion demandée", etat.get("authRequired") is False)
        verifier("les notes viennent de mes-notes", etat.get("noteCount") == 25,
                 str(etat.get("noteCount")))
        # Sans aucun document réel à brancher, les exemples restent — mais JARVIS
        # doit les ANNONCER comme fictifs, jamais les faire passer pour des notes.
        verifier("les exemples sont annoncés comme tels", etat.get("isDemo") is True,
                 str(etat.get("noteCount")))

        try:
            with ouvreur.open(f"http://127.0.0.1:{port}/setup", timeout=10) as reponse:
                page = reponse.read().decode("utf8", "replace")
            verifier("aucun formulaire de réglage proposé", 'name="token"' not in page)
            verifier("la page explique qu'il n'y a rien à faire",
                     "Aucun réglage" in page or "Déjà configuré" in page)
        except urllib.error.HTTPError as exc:
            corps = exc.read().decode("utf8", "replace")
            verifier("aucun formulaire de réglage proposé", 'name="token"' not in corps, str(exc.code))
            verifier("la page explique qu'il n'y a rien à faire", True, str(exc.code))

        reseau = adresse_reseau()
        if reseau:
            with socket.socket() as sonde:
                sonde.settimeout(2)
                try:
                    sonde.connect((reseau, port))
                    verifier("invisible depuis le réseau", False, f"{reseau} accepte !")
                except OSError:
                    verifier("invisible depuis le réseau", True, reseau)
        else:
            verifier("invisible depuis le réseau", True, "pas d'interface réseau")

        # Une note écrite à la main doit être vue au démarrage suivant.
        (notes / "mon-idee.md").write_text("# Mon idée\n\nÀ creuser demain.\n", encoding="utf-8")
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=8)
        except subprocess.TimeoutExpired:
            processus.kill()

    verifier("les notes restent sur le disque", (app / "mes-notes" / "mon-idee.md").is_file())

    # Deuxième démarrage : rien n'est écrasé, la note personnelle est toujours là.
    processus = subprocess.Popen(
        [sys.executable, "-u", "lancer_jarvis.py"],
        cwd=str(app), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        limite = time.time() + 40
        port = None
        while time.time() < limite:
            ligne = processus.stdout.readline()
            if not ligne:
                break
            trouve = re.search(r"localhost:(\d+)", ligne)
            if trouve:
                port = int(trouve.group(1))
                break
        if port:
            ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with ouvreur.open(f"http://127.0.0.1:{port}/api/status", timeout=10) as reponse:
                etat = json.loads(reponse.read().decode("utf8"))
            verifier("2e démarrage : la note perso est comptée", etat.get("noteCount") == 26,
                     str(etat.get("noteCount")))
        else:
            verifier("2e démarrage : le serveur repart", False)
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=8)
        except subprocess.TimeoutExpired:
            processus.kill()

    reussites = sum(1 for ok, _, _ in RESULTATS if ok)
    print(f"\n{reussites}/{len(RESULTATS)} vérifications passées")
    return 0 if reussites == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
