#!/usr/bin/env python3
"""La porte de JARVIS doit se fermer, jamais s'ouvrir, en cas de mauvaise configuration.

Deux scénarios, sur de vrais serveurs lancés avec de vraies variables d'environnement :

1. identifiants Google présents mais liste d'adresses vide → personne n'entre ;
2. adresse collée avec des guillemets ou des espaces → elle est quand même lue.

Usage : python3 tests/test_gate.py
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS: list[tuple[bool, str, str]] = []

# Aucun intermédiaire réseau : on parle directement au serveur local.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


STATIC = urllib.request.build_opener(urllib.request.ProxyHandler({}), SansRedirection)


def check(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((ok, label, detail))
    print(f"{'OK  ' if ok else 'ÉCHEC'} {label:<48} {detail}")


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def attendre(port: int, delai: float = 20.0) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def copie_du_projet() -> Path:
    """Copie le code dans un dossier neuf, SANS config.json.

    Indispensable : un config.json présent sur la machine de développement
    fournirait lui-même des adresses autorisées, et le test ne testerait plus
    la configuration qu'on lui donne.
    """
    import shutil

    app = Path(tempfile.mkdtemp(prefix="jarvis-gate-app-"))
    for fichier in sorted(ROOT.glob("*.py")):
        shutil.copy2(fichier, app / fichier.name)
    shutil.copy2(ROOT / "config.example.json", app / "config.example.json")
    for dossier in ("viewer", "examples"):
        (app / dossier).symlink_to(ROOT / dossier, target_is_directory=True)
    return app


def demarrer(port: int, **env_sup: str) -> tuple[subprocess.Popen, Path]:
    donnees = Path(tempfile.mkdtemp(prefix="jarvis-gate-"))
    app = copie_du_projet()
    env = dict(os.environ)
    env.update({
        "PORT": str(port),
        "JARVIS_HOST": "127.0.0.1",
        "JARVIS_DATA_DIR": str(donnees / "data"),
        "JARVIS_ACCESS_PATH": str(donnees / "access.json"),
        "JARVIS_PUBLIC_URL": "https://jarvis-lowrenzu.onrender.com",
        "JARVIS_GOOGLE_CLIENT_ID": "1005904286480-test.apps.googleusercontent.com",
        "JARVIS_GOOGLE_CLIENT_SECRET": "secret-de-test",
        "JARVIS_NOTES_DIR": str(ROOT / "examples" / "demo-notes"),
    })
    env.pop("JARVIS_AUTH", None)
    env.update(env_sup)
    proc = subprocess.Popen(
        [sys.executable, "-u", "server.py"],
        cwd=str(app), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if not attendre(port):
        proc.kill()
        sortie = proc.stdout.read() if proc.stdout else ""
        raise RuntimeError(f"le serveur n'a pas démarré :\n{sortie}")
    return proc, donnees


def status(url: str) -> tuple[int, str]:
    try:
        with STATIC.open(url, timeout=10) as reponse:
            return reponse.status, reponse.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Location", "")


def scenario_liste_vide() -> None:
    port = port_libre()
    proc, _ = demarrer(port, JARVIS_ALLOWED_EMAILS="", JARVIS_ADMIN_EMAIL="")
    base = f"http://127.0.0.1:{port}"
    try:
        code, lieu = status(base + "/")
        check("liste vide : l'accueil renvoie vers la connexion", code == 302 and "login" in lieu, f"{code} {lieu}")
        code, _ = status(base + "/api/status")
        check("liste vide : les données sont refusées", code == 401, str(code))
        code, _ = status(base + "/auth/login")
        check("liste vide : la page explique le problème", code == 200, str(code))
        code, _ = status(base + "/api/session")
        check("liste vide : le contrôle de santé passe", code == 200, str(code))
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def scenario_adresse_entre_guillemets() -> None:
    port = port_libre()
    proc, donnees = demarrer(
        port,
        JARVIS_ALLOWED_EMAILS='  "funk.e.lee@gmail.com"  ',
        JARVIS_ADMIN_EMAIL="funk.e.lee@gmail.com",
    )
    base = f"http://127.0.0.1:{port}"
    try:
        import json
        access = json.loads((donnees / "access.json").read_text(encoding="utf-8"))
        check("guillemets : l'adresse est lue", len(access.get("emails") or []) == 1,
              str(access.get("emails")))
        check("guillemets : l'administrateur est reconnu",
              access.get("admin") == "funk.e.lee@gmail.com", str(access.get("admin")))
        code, lieu = status(base + "/")
        check("guillemets : la porte est armée", code == 302 and "login" in lieu, f"{code} {lieu}")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def main() -> int:
    try:
        scenario_liste_vide()
        scenario_adresse_entre_guillemets()
    except Exception as exc:  # noqa: BLE001
        print(f"ÉCHEC du harnais : {type(exc).__name__}: {exc}")
        return 1
    reussites = sum(1 for ok, _, _ in RESULTS if ok)
    print(f"\n{reussites}/{len(RESULTS)} vérifications passées")
    return 0 if reussites == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
