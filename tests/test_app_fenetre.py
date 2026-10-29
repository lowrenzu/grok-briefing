#!/usr/bin/env python3
"""La fenêtre d'application : code testé sans écran.

pywebview ne peut pas ouvrir de fenêtre dans un environnement sans affichage.
On installe donc un faux module `webview` qui enregistre ce qu'on lui demande,
puis on vérifie trois choses :

1. la fenêtre reçoit bien l'adresse locale de JARVIS ;
2. fermer la fenêtre arrête le serveur (le script se termine proprement) ;
3. sans pywebview, le repli vers le navigateur fonctionne toujours.

Usage : python3 tests/test_app_fenetre.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTATS: list[tuple[bool, str, str]] = []

FAUX_WEBVIEW = '''"""Faux pywebview pour les tests : enregistre les appels, sans afficher."""
import json, os

RECORD = os.environ.get("FAUX_WEBVIEW_FICHIER", "")

def create_window(titre, adresse, **options):
    if RECORD:
        with open(RECORD, "w", encoding="utf-8") as fh:
            json.dump({"titre": titre, "adresse": adresse, "options": options}, fh)
    return object()

def start(*args, **kwargs):
    # Simule la fermeture de la fenêtre par l'utilisateur.
    return None
'''


def verifier(label: str, ok: bool, detail: str = "") -> None:
    RESULTATS.append((ok, label, detail))
    print(f"{'OK  ' if ok else 'ÉCHEC'} {label:<50} {detail}")


def copie_neuve() -> Path:
    app = Path(tempfile.mkdtemp(prefix="jarvis-fenetre-app-"))
    for fichier in ("server.py", "access.py", "auth.py", "prefs.py", "setup.py",
                    "workspaces.py", "ai_providers.py", "build.py", "lancer_jarvis.py"):
        shutil.copy2(ROOT / fichier, app / fichier)
    for dossier in ("viewer", "examples"):
        (app / dossier).symlink_to(ROOT / dossier, target_is_directory=True)
    return app


def environnement(dossier_faux: Path | None, trace: Path, sans_navigateur: bool = True) -> dict[str, str]:
    env = {cle: valeur for cle, valeur in os.environ.items() if not cle.startswith("JARVIS_")}
    if sans_navigateur:
        # Supprime navigateur ET fenêtre : mode « tête baissée », pour les tests.
        env["JARVIS_NO_BROWSER"] = "1"
    env["FAUX_WEBVIEW_FICHIER"] = str(trace)
    if dossier_faux:
        env["PYTHONPATH"] = str(dossier_faux) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def demarrer_lecture(processus: subprocess.Popen) -> list[str]:
    """Consomme la sortie en tâche de fond.

    Nécessaire : `select` ne voit pas les lignes déjà présentes dans le tampon
    de Python, et une lecture bloquante figerait le test.
    """
    import threading

    lignes: list[str] = []

    def boucle() -> None:
        flux = processus.stdout
        if flux is None:
            return
        for ligne in flux:
            lignes.append(ligne.rstrip())

    threading.Thread(target=boucle, daemon=True).start()
    return lignes


def lancer(app: Path, env: dict[str, str], delai: float = 40.0) -> tuple[int, list[str]]:
    processus = subprocess.Popen(
        [sys.executable, "-u", "lancer_jarvis.py"], cwd=str(app), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    lignes = demarrer_lecture(processus)
    limite = time.time() + delai
    try:
        while time.time() < limite:
            if processus.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        if processus.poll() is None:
            processus.terminate()
            try:
                processus.wait(timeout=8)
            except subprocess.TimeoutExpired:
                processus.kill()
    return processus.returncode, lignes


def scenario_fenetre() -> None:
    app = copie_neuve()
    faux = Path(tempfile.mkdtemp(prefix="faux-webview-"))
    (faux / "webview.py").write_text(FAUX_WEBVIEW, encoding="utf-8")
    trace = Path(tempfile.mkdtemp(prefix="trace-webview-")) / "appel.json"

    code, lignes = lancer(app, environnement(faux, trace, sans_navigateur=False))
    verifier("la fenêtre est demandée", trace.is_file())
    if trace.is_file():
        appel = json.loads(trace.read_text(encoding="utf-8"))
        verifier("le titre est JARVIS", appel.get("titre") == "JARVIS", str(appel.get("titre")))
        adresse = appel.get("adresse", "")
        verifier("l'adresse est locale", adresse.startswith("http://localhost:"), adresse)
        verifier("une taille de fenêtre est fixée",
                 appel.get("options", {}).get("width", 0) >= 1000,
                 str(appel.get("options", {}).get("width")))
    verifier("fermer la fenêtre termine JARVIS", code == 0, str(code))
    verifier("aucun message d'erreur", not any("indisponible" in ligne for ligne in lignes))


def scenario_repli() -> None:
    """Sans pywebview : le serveur démarre et reste debout, prêt à s'ouvrir."""
    app = copie_neuve()
    trace = Path(tempfile.mkdtemp(prefix="trace-vide-")) / "inutile.json"
    # Navigateur autorisé (sinon le message de repli n'est pas affiché), mais
    # $BROWSER neutralisé : aucune fenêtre ne doit s'ouvrir pendant le test.
    env = environnement(None, trace, sans_navigateur=False)
    env.pop("PYTHONPATH", None)
    env["BROWSER"] = "/bin/true"

    processus = subprocess.Popen(
        [sys.executable, "-u", "lancer_jarvis.py"], cwd=str(app), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    lignes = demarrer_lecture(processus)
    port = None
    try:
        limite = time.time() + 40
        while time.time() < limite:
            for ligne in list(lignes):
                trouve = re.search(r"localhost:(\d+)", ligne)
                if trouve:
                    port = int(trouve.group(1))
                    break
            if port:
                break
            time.sleep(0.15)
        verifier("sans pywebview, le serveur démarre", port is not None, str(port))
        verifier("aucune fenêtre n'est demandée", not trace.is_file())
        time.sleep(1.0)  # laisse le message de repli arriver
        texte = "\n".join(lignes)
        verifier("le repli est annoncé clairement",
                 "indisponible" in texte and "navigateur" in texte)
        verifier("l'installation de la fenêtre est indiquée",
                 "INSTALLER-APPLICATION.bat" in texte)
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=8)
        except subprocess.TimeoutExpired:
            processus.kill()


def main() -> int:
    try:
        scenario_fenetre()
        scenario_repli()
    except Exception as exc:  # noqa: BLE001
        print(f"ÉCHEC du harnais : {type(exc).__name__}: {exc}")
        return 1
    reussites = sum(1 for ok, _, _ in RESULTATS if ok)
    print(f"\n{reussites}/{len(RESULTATS)} vérifications passées")
    return 0 if reussites == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
