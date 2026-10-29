#!/usr/bin/env python3
"""Premier réglage : JARVIS se configure sans qu'aucun secret ne circule.

Ce test lance un vrai serveur, sans config.json, puis vérifie que :

1. depuis Internet, tout renvoie vers /setup (le cockpit n'est pas servi) ;
2. en local, l'interface reste consultable ;
3. un mauvais code d'installation est refusé ;
4. un identifiant Google invalide est refusé ;
5. le bon formulaire écrit config.json (0600), arme la porte Google ;
6. /setup se referme définitivement et le code est effacé.

Usage : python3 tests/test_setup.py
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
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTATS: list[tuple[bool, str, str]] = []
CLIENT_ID = "123456789000-testfactice000000000000000000.apps.googleusercontent.com"
SECRET = "secret-de-test-factice-0123456789abc"
PUBLIC = "jarvis.exemple.fr"


class SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def verifier(label: str, ok: bool, detail: str = "") -> None:
    RESULTATS.append((ok, label, detail))
    print(f"{'OK  ' if ok else 'ÉCHEC'} {label:<50} {detail}")


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def copie_du_projet() -> Path:
    app = Path(tempfile.mkdtemp(prefix="jarvis-setup-app-"))
    for fichier in ("server.py", "access.py", "auth.py", "prefs.py", "setup.py",
                    "workspaces.py", "ai_providers.py", "build.py"):
        shutil.copy2(ROOT / fichier, app / fichier)
    for dossier in ("viewer", "examples"):
        (app / dossier).symlink_to(ROOT / dossier, target_is_directory=True)
    return app


def attendre(port: int, delai: float = 20.0) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def demarrer(port: int, donnees: Path, **env_sup: str) -> tuple[subprocess.Popen, Path]:
    app = copie_du_projet()
    env = dict(os.environ)
    env.update({
        "PORT": str(port),
        "JARVIS_HOST": "127.0.0.1",
        "JARVIS_DATA_DIR": str(donnees / "data"),
        "JARVIS_ACCESS_PATH": str(donnees / "access.json"),
        "JARVIS_NOTES_DIR": str(ROOT / "examples" / "demo-notes"),
    })
    for cle in ("JARVIS_AUTH", "JARVIS_GOOGLE_CLIENT_ID", "JARVIS_GOOGLE_CLIENT_SECRET",
                "JARVIS_ALLOWED_EMAILS", "JARVIS_PUBLIC_URL"):
        env.pop(cle, None)
    env.update(env_sup)
    proc = subprocess.Popen([sys.executable, "-u", "server.py"], cwd=str(app), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if not attendre(port):
        proc.kill()
        raise RuntimeError("le serveur n'a pas démarré")
    return proc, app


def requete(port: int, chemin: str, *, host: str | None = None, donnees: dict | None = None,
            suivre: bool = False) -> tuple[int, str, str]:
    entetes = {}
    if host:
        entetes["Host"] = host
    corps = None
    if donnees is not None:
        corps = urllib.parse.urlencode(donnees).encode()
        entetes["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{chemin}", data=corps, headers=entetes)
    handlers = [urllib.request.ProxyHandler({})]
    if not suivre:
        handlers.append(SansRedirection)
    else:
        handlers.append(urllib.request.HTTPCookieProcessor())
    ouvreur = urllib.request.build_opener(*handlers)
    try:
        with ouvreur.open(req, timeout=15) as reponse:
            return reponse.status, reponse.headers.get("Location", ""), reponse.read(8000).decode("utf8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Location", ""), exc.read(8000).decode("utf8", "replace")


def scenario_reglage() -> None:
    port = port_libre()
    donnees = Path(tempfile.mkdtemp(prefix="jarvis-setup-"))
    proc, app = demarrer(port, donnees)
    try:
        jeton_fichier = donnees / "data" / "setup-token.txt"
        verifier("un code d'installation est écrit", jeton_fichier.is_file())
        mode = oct(jeton_fichier.stat().st_mode)[-3:] if jeton_fichier.is_file() else "?"
        verifier("le code est privé (0600)", mode == "600", mode)
        jeton = jeton_fichier.read_text().strip() if jeton_fichier.is_file() else ""
        verifier("le code fait 8 caractères", len(jeton) == 8, jeton)

        code, lieu, _ = requete(port, "/", host=PUBLIC)
        verifier("depuis Internet : renvoi vers /setup", code == 302 and lieu.endswith("/setup"), f"{code} {lieu}")
        code, _, _ = requete(port, "/api/status", host=PUBLIC)
        verifier("depuis Internet : les données sont refusées", code == 503, str(code))
        code, _, _ = requete(port, "/api/session", host=PUBLIC)
        verifier("le contrôle de santé passe", code == 200, str(code))
        code, _, _ = requete(port, "/setup", host=PUBLIC)
        verifier("la page de réglage s'ouvre", code == 200, str(code))

        code, _, _ = requete(port, "/", host="localhost")
        verifier("en local, l'interface reste consultable", code == 200, str(code))

        code, _, _ = requete(port, "/setup", host=PUBLIC,
                             donnees={"token": "mauvais", "client_id": CLIENT_ID,
                                      "client_secret": SECRET, "admin_email": "a@b.fr"})
        verifier("un mauvais code est refusé", code == 400, str(code))

        code, _, _ = requete(port, "/setup", host=PUBLIC,
                             donnees={"token": jeton, "client_id": "pas-un-identifiant",
                                      "client_secret": SECRET, "admin_email": "a@b.fr"})
        verifier("un identifiant Google invalide est refusé", code == 400, str(code))

        code, _, _ = requete(port, "/setup", host=PUBLIC,
                             donnees={"token": jeton, "client_id": CLIENT_ID,
                                      "client_secret": SECRET, "admin_email": "pas un mail"})
        verifier("une adresse invalide est refusée", code == 400, str(code))

        code, _, _ = requete(port, "/setup", host=PUBLIC,
                             donnees={"token": jeton, "client_id": CLIENT_ID,
                                      "client_secret": SECRET, "admin_email": "funk.e.lee@gmail.com"})
        verifier("le bon formulaire est accepté", code == 200, str(code))

        ecrit_config = app / "config.json"
        verifier("config.json est écrit", ecrit_config.is_file())

        code, lieu, _ = requete(port, "/", host=PUBLIC)
        verifier("la porte Google est armée", code == 302 and "login" in lieu, f"{code} {lieu}")
        code, _, _ = requete(port, "/setup", host=PUBLIC)
        verifier("/setup se referme définitivement", code == 410, str(code))
        verifier("le code d'installation est effacé", not jeton_fichier.exists())

        ecrit = json.loads(ecrit_config.read_text(encoding="utf-8"))["auth"]
        verifier("l'adresse publique est déduite",
                 ecrit.get("public_url") == f"http://{PUBLIC}", str(ecrit.get("public_url")))
        verifier("l'administrateur est enregistré",
                 ecrit.get("admin_email") == "funk.e.lee@gmail.com")
        verifier("config.json est privé (0600)",
                 oct(ecrit_config.stat().st_mode)[-3:] == "600",
                 oct(ecrit_config.stat().st_mode)[-3:])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def scenario_developpement() -> None:
    """JARVIS_AUTH=off reste une échappatoire : le mur ne s'applique pas."""
    port = port_libre()
    donnees = Path(tempfile.mkdtemp(prefix="jarvis-setup-dev-"))
    proc, _app = demarrer(port, donnees, JARVIS_AUTH="off")
    try:
        code, _, _ = requete(port, "/", host=PUBLIC)
        verifier("mode développement : l'interface s'ouvre", code == 200, str(code))
        code, _, corps = requete(port, "/setup", host=PUBLIC)
        verifier("mode développement : aucun formulaire de réglage",
                 code == 200 and 'name="token"' not in corps, str(code))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def scenario_config_minimale() -> None:
    """Le mode d'installation sans secret écrit un config.json sans identifiants."""
    port = port_libre()
    donnees = Path(tempfile.mkdtemp(prefix="jarvis-setup-min-"))
    proc, app = demarrer(port, donnees)
    proc.terminate()
    proc.wait(timeout=5)

    (app / "config.json").write_text('{"notes_dir": "examples/demo-notes"}', encoding="utf-8")
    proc, app = demarrer(port, donnees)
    try:
        code, lieu, _ = requete(port, "/", host=PUBLIC)
        verifier("config sans identifiants : mur actif", code == 302 and lieu.endswith("/setup"),
                 f"{code} {lieu}")
        jeton = donnees / "data" / "setup-token.txt"
        verifier("config sans identifiants : code fourni", jeton.is_file())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def scenario_identifiants_par_environnement() -> None:
    """Hébergeur sans disque : les identifiants viennent de l'environnement.

    C'est le cas de Render gratuit, où config.json ne survit pas. La page
    /setup n'a alors aucun sens : elle serait effacée au réveil suivant.
    """
    port = port_libre()
    donnees = Path(tempfile.mkdtemp(prefix="jarvis-setup-env-"))
    proc, app = demarrer(
        port, donnees,
        JARVIS_GOOGLE_CLIENT_ID="123456789000-envtest00000000000000000000.apps.googleusercontent.com",
        JARVIS_GOOGLE_CLIENT_SECRET="secret-d-environnement-pour-le-test",
        JARVIS_ALLOWED_EMAILS="moi@exemple.fr",
        JARVIS_ADMIN_EMAIL="moi@exemple.fr",
        JARVIS_PUBLIC_URL="https://mon-service.exemple.fr",
    )
    try:
        code, lieu, _ = requete(port, "/", host=PUBLIC)
        verifier("env : pas de mur vers /setup", code == 302 and "login" in lieu, f"{code} {lieu}")
        code, _, _ = requete(port, "/setup", host=PUBLIC)
        verifier("env : /setup est fermé (déjà configuré)", code == 410, str(code))
        code, _, _ = requete(port, "/api/status", host=PUBLIC)
        verifier("env : les données restent protégées", code == 401, str(code))
        code, _, _ = requete(port, "/api/session", host=PUBLIC)
        verifier("env : le contrôle de santé passe", code == 200, str(code))
        verifier("env : aucun code d'installation n'est créé",
                 not (donnees / "data" / "setup-token.txt").exists())
        verifier("env : aucun config.json n'est écrit", not (app / "config.json").exists())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def scenario_environnement_sans_adresse() -> None:
    """Identifiants en environnement mais liste d'adresses vide : on ferme.

    Le serveur ne doit jamais se rabattre sur un accès ouvert : il renvoie vers
    la page de connexion, qui explique le problème.
    """
    port = port_libre()
    donnees = Path(tempfile.mkdtemp(prefix="jarvis-setup-env-vide-"))
    proc, _app = demarrer(
        port, donnees,
        JARVIS_GOOGLE_CLIENT_ID="123456789000-envtest00000000000000000000.apps.googleusercontent.com",
        JARVIS_GOOGLE_CLIENT_SECRET="secret-d-environnement-pour-le-test",
        JARVIS_ALLOWED_EMAILS="",
    )
    try:
        code, lieu, _ = requete(port, "/", host=PUBLIC)
        verifier("env sans adresse : porte fermée", code == 302 and "login" in lieu, f"{code} {lieu}")
        code, _, _ = requete(port, "/api/status", host=PUBLIC)
        verifier("env sans adresse : données refusées", code == 401, str(code))
        code, _, corps = requete(port, "/auth/login", host=PUBLIC)
        verifier("env sans adresse : la page explique", code == 200 and "adresse" in corps.lower(),
                 str(code))
        code, _, _ = requete(port, "/api/session", host=PUBLIC)
        verifier("env sans adresse : contrôle de santé actif", code == 200, str(code))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    try:
        scenario_reglage()
        scenario_config_minimale()
        scenario_identifiants_par_environnement()
        scenario_environnement_sans_adresse()
        scenario_developpement()
    except Exception as exc:  # noqa: BLE001
        print(f"ÉCHEC du harnais : {type(exc).__name__}: {exc}")
        return 1
    reussites = sum(1 for ok, _, _ in RESULTATS if ok)
    print(f"\n{reussites}/{len(RESULTATS)} vérifications passées")
    return 0 if reussites == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
