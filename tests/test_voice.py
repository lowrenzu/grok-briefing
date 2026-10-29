#!/usr/bin/env python3
"""La voix de JARVIS : neuronale quand c'est possible, jamais muette sinon.

Vérifie trois choses, sans réseau et sans son :

1. le module `voice.py` choisit une voix française et nettoie le texte ;
2. le serveur rend un vrai fichier audio sur `/api/voice` ;
3. quand le service est indisponible, la réponse est un 503 explicite — le
   signal qui fait basculer l'interface sur la voix du navigateur.

Usage : python3 tests/test_voice.py
"""
from __future__ import annotations

import json
import os
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
TESTS = Path(__file__).resolve().parent
RESULTATS: list[tuple[bool, str, str]] = []


def verifier(label: str, ok: bool, detail: str = "") -> None:
    RESULTATS.append((ok, label, detail))
    print(f"{'OK  ' if ok else 'ÉCHEC'} {label:<52} {detail}")


def port_libre() -> int:
    with socket.socket() as prise:
        prise.bind(("127.0.0.1", 0))
        return prise.getsockname()[1]


# --- 1. le module seul ------------------------------------------------------
sys.path.insert(0, str(ROOT))
import voice  # noqa: E402

verifier("une voix française par défaut", voice.VOIX_PAR_DEFAUT.startswith("fr-FR"),
         voice.VOIX_PAR_DEFAUT)
verifier("plusieurs voix proposées", len(voice.VOIX_DISPONIBLES) >= 2,
         ", ".join(voice.VOIX_DISPONIBLES))
verifier("nettoyage des espaces", voice.nettoyer("  Bonjour\n\n  monsieur  ") == "Bonjour monsieur")
verifier("texte vide → rien", voice.synthese("   ") is None)
verifier("texte limité en longueur", len(voice.nettoyer("a" * 5000)) == voice.MAX_CARACTERES)

etat = voice.etat()
verifier("état lisible par l'interface", {"neural", "voice", "voices"} <= set(etat))
verifier("repli annoncé", etat["fallback"] == "navigateur")

# --- 2. avec un faux service (aucun réseau) ---------------------------------
tmp = Path(tempfile.mkdtemp(prefix="jarvis-voix-"))
# Le faux service doit porter le nom du vrai paquet pour être importé tel quel.
shutil.copy2(TESTS / "fake_edge_tts.py", tmp / "edge_tts.py")
compte = tmp / "appels.txt"
panne = tmp / "panne"
env = {k: v for k, v in os.environ.items() if not k.startswith("JARVIS_")}
env.update(
    PORT=str(port_libre()),
    JARVIS_HOST="127.0.0.1",
    JARVIS_AUTH="off",
    JARVIS_DATA_DIR=str(tmp / "data"),
    JARVIS_NOTES_DIR=str(tmp / "notes"),
    JARVIS_ACCESS_PATH=str(tmp / "access.json"),
    PYTHONPATH=str(tmp),
    FAKE_EDGE_TTS_COMPTE=str(compte),
    FAKE_EDGE_TTS_PANNE=str(panne),
)
BASE = f"http://127.0.0.1:{env['PORT']}"
serveur = subprocess.Popen([sys.executable, "-u", "server.py"], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def debout() -> bool:
    for _ in range(80):
        try:
            urllib.request.urlopen(f"{BASE}/api/voice", timeout=1)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(0.2)
    return False


def post(charge: dict[str, object]) -> tuple[int, bytes, str]:
    requete = urllib.request.Request(
        f"{BASE}/api/voice",
        data=json.dumps(charge).encode("utf8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requete, timeout=20) as reponse:
            return reponse.status, reponse.read(), reponse.headers.get("Content-Type", "")
    except urllib.error.HTTPError as erreur:
        return erreur.code, erreur.read(), erreur.headers.get("Content-Type", "")


try:
    if not debout():
        verifier("le serveur démarre", False)
        raise SystemExit(1)

    with urllib.request.urlopen(f"{BASE}/api/voice", timeout=5) as reponse:
        statut_voix = json.loads(reponse.read().decode("utf8"))
    verifier("le serveur annonce la voix neuronale", statut_voix.get("neural") is True)
    verifier("la voix d'usine est française",
             str(statut_voix.get("voice", "")).startswith("fr-FR"), str(statut_voix.get("voice")))

    code, corps, type_contenu = post({"text": "Bonjour, monsieur. Tout est en ordre."})
    verifier("phrase rendue en audio", code == 200 and corps.startswith(b"ID3FAKE"),
             f"{code} · {len(corps)} octets")
    verifier("type audio correct", type_contenu.startswith("audio/mpeg"), type_contenu)

    appels = compte.read_text(encoding="utf8").splitlines() if compte.is_file() else []
    verifier("voix par défaut utilisée", appels and appels[0].startswith(voice.VOIX_PAR_DEFAUT + "\t"),
             appels[0] if appels else "aucun appel")

    post({"text": "Bonjour, monsieur. Tout est en ordre."})
    appels = compte.read_text(encoding="utf8").splitlines()
    verifier("une phrase identique n'est demandée qu'une fois", len(appels) == 1, f"{len(appels)} appel(s)")

    post({"text": "Autre phrase.", "voice": "Denise"})
    appels = compte.read_text(encoding="utf8").splitlines()
    verifier("la voix choisie est respectée",
             appels[-1].startswith(voice.VOIX_DISPONIBLES["Denise"] + "\t"), appels[-1].split("\t")[0])

    post({"text": "Voix inventée.", "voice": "Robot-9000"})
    appels = compte.read_text(encoding="utf8").splitlines()
    verifier("une voix inconnue retombe sur celle d'usine",
             appels[-1].startswith(voice.VOIX_PAR_DEFAUT + "\t"), appels[-1].split("\t")[0])

    code, _corps, _type = post({"text": "   \n  "})
    verifier("texte vide refusé", code == 400, str(code))

    code, corps, type_contenu = post({"text": "Bonjour.\n\nMonsieur   comment ?"})
    appels = compte.read_text(encoding="utf8").splitlines()
    verifier("texte nettoyé avant lecture",
             appels[-1].split("\t", 1)[1] == "Bonjour. Monsieur comment ?", appels[-1].split("\t", 1)[1])

    # Service en panne : 503 explicite, jamais une erreur 500.
    panne.write_text("1", encoding="utf8")
    code, corps, _type = post({"text": "Phrase jamais prononcée."})
    verifier("service indisponible → 503", code == 503, str(code))
    try:
        detail = json.loads(corps.decode("utf8"))
    except ValueError:
        detail = {}
    verifier("le repli navigateur est annoncé", detail.get("fallback") == "browser", str(detail))
    panne.unlink()

    # --- 3. sans edge-tts installé : silence propre, pas de plantage -------
    sans_paquet = subprocess.run(
        [sys.executable, "-c",
         "import json, voice; print(json.dumps({'etat': voice.etat()['neural'], "
         "'son': voice.synthese('Bonjour')}))"],
        cwd=ROOT,
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        capture_output=True, text=True, timeout=60,
    )
    resultat = json.loads(sans_paquet.stdout or "{}")
    verifier("sans le paquet : pas de voix neuronale", resultat.get("etat") is False, str(resultat))
    verifier("sans le paquet : renvoie None sans erreur", resultat.get("son") is None)
finally:
    serveur.terminate()
    try:
        serveur.wait(timeout=10)
    except subprocess.TimeoutExpired:
        serveur.kill()
    shutil.rmtree(tmp, ignore_errors=True)

total = len(RESULTATS)
reussites = sum(1 for ok, _label, _detail in RESULTATS if ok)
print(f"\n{reussites}/{total} vérifications passées")
raise SystemExit(0 if reussites == total else 1)
