#!/usr/bin/env python3
"""Lance JARVIS sur cet ordinateur, sans réglage ni compte.

Double-clic sur le fichier correspondant à votre système :
    Windows  : LANCER-JARVIS.bat
    Mac      : Lancer-JARVIS.command

Ce que fait ce script, dans l'ordre :
  1. il crée un dossier « mes-notes » à côté de lui, et y copie une première
     fois les notes d'exemple (une seule fois : ensuite il n'y touche plus) ;
  2. il démarre JARVIS en écoute uniquement sur cet ordinateur (127.0.0.1),
     donc invisible depuis le réseau ou Internet ;
  3. il ouvre votre navigateur sur la page d'accueil.

Vos notes restent dans « mes-notes », sur votre disque. Rien ne part ailleurs.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
NOTES = BASE / "mes-notes"
EXEMPLES = BASE / "examples" / "demo-notes"
PORT_PREFERE = 4700


def dire(message: str) -> None:
    print(message, flush=True)


def port_libre(depart: int) -> int:
    """Cherche un port disponible, en commençant par le préféré."""
    for port in range(depart, depart + 20):
        with socket.socket() as essai:
            try:
                essai.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Aucun port libre entre 4700 et 4719.")


def preparer_notes() -> None:
    """Première fois : un vrai dossier de notes, copié depuis les exemples."""
    if NOTES.is_dir():
        return
    NOTES.mkdir(parents=True, exist_ok=True)
    copies = 0
    if EXEMPLES.is_dir():
        for fichier in sorted(EXEMPLES.glob("*.md")):
            try:
                shutil.copy2(fichier, NOTES / fichier.name)
                copies += 1
            except OSError:
                pass
    dire(f"  Dossier de notes créé : {NOTES}")
    if copies:
        dire(f"  {copies} notes d’exemple copiées (vous pouvez les modifier ou les supprimer).")


def attendre(port: int, delai: float = 30.0) -> bool:
    fin = time.time() + delai
    ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.time() < fin:
        try:
            with ouvreur.open(f"http://127.0.0.1:{port}/api/session", timeout=1) as reponse:
                if reponse.status == 200:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.25)
    return False


def fenetre_disponible() -> bool:
    """Vrai si une vraie fenêtre d'application peut être ouverte."""
    if os.environ.get("JARVIS_NAVIGATEUR") == "1":
        return False
    try:
        import webview  # noqa: F401  (présence seulement)
    except Exception:  # noqa: BLE001 - absence ou WebView2 indisponible
        return False
    return True


def ouvrir_fenetre(adresse: str) -> bool:
    """Ouvre JARVIS dans sa propre fenêtre, sans navigateur autour.

    Bloque jusqu'à ce que la fenêtre soit fermée : fermer la fenêtre arrête
    JARVIS. Renvoie False si ce n'est pas possible, pour laisser la main au
    navigateur — jamais d'échec bloquant.
    """
    try:
        import webview
    except Exception:  # noqa: BLE001
        return False

    try:
        webview.create_window(
            "JARVIS",
            adresse,
            width=1360,
            height=900,
            min_size=(960, 640),
            background_color="#070b12",
            text_select=True,
        )
        webview.start()
        return True
    except Exception as exc:  # noqa: BLE001 - on continue dans le navigateur
        dire(f"  Fenêtre indisponible ({type(exc).__name__}) : ouverture dans le navigateur.")
        return False


def main() -> int:
    if not (BASE / "server.py").is_file():
        dire("  Ce fichier doit rester à côté de server.py, dans le dossier JARVIS.")
        return 1

    dire("")
    dire("  JARVIS — démarrage sur cet ordinateur")
    dire("  ─────────────────────────────────────────────────")

    preparer_notes()
    port = port_libre(PORT_PREFERE)

    environnement = dict(os.environ)
    environnement.update({
        # Écoute locale uniquement : le reste du réseau n'y a pas accès.
        "JARVIS_HOST": "127.0.0.1",
        # Pas de connexion Google : un seul utilisateur, sur son propre PC.
        "JARVIS_AUTH": "off",
        "JARVIS_NOTES_DIR": str(NOTES),
        "PORT": str(port),
    })

    processus = subprocess.Popen(
        [sys.executable, "-u", "server.py"],
        cwd=str(BASE), env=environnement,
    )

    adresse = f"http://localhost:{port}"
    try:
        if not attendre(port):
            dire("")
            dire("  Le serveur n’a pas démarré. La fenêtre reste ouverte pour lire l’erreur.")
            return 1
        dire("")
        dire(f"  Adresse : {adresse}")

        # 1) La vraie fenêtre d'application, si pywebview est disponible.
        if fenetre_disponible() and os.environ.get("JARVIS_NO_BROWSER") != "1":
            dire("  Ouverture de la fenêtre JARVIS. La fermer arrête tout.")
            dire("")
            if ouvrir_fenetre(adresse):
                return 0

        # 2) Sinon, le navigateur — et JARVIS reste simple à utiliser.
        dire("  Pour arrêter JARVIS : fermez cette fenêtre, ou Ctrl+C.")
        dire("")
        if os.environ.get("JARVIS_NO_BROWSER") != "1":
            try:
                webbrowser.open(adresse)
            except Exception:  # noqa: BLE001 - un navigateur absent n'est pas une panne
                dire(f"  Ouvrez cette adresse dans votre navigateur : {adresse}")
        return processus.wait()
    except KeyboardInterrupt:
        dire("\n  Arrêt demandé.")
        return 0
    finally:
        if processus.poll() is None:
            processus.terminate()
            try:
                processus.wait(timeout=5)
            except subprocess.TimeoutExpired:
                processus.kill()


if __name__ == "__main__":
    sys.exit(main())
