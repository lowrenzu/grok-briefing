#!/usr/bin/env python3
"""Vérifie que chaque compte a bien son propre JARVIS.

Scénario : deux personnes autorisées se connectent en même temps, via un faux
Google local. On vérifie que ni les notes, ni les souvenirs, ni le graphe, ni la
liste des comptes ne passent d'un espace à l'autre.

    python3 tests/test_isolation.py
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
PORT = int(os.environ.get("JARVIS_TEST_PORT", "4741"))
FAKE_PORT = os.environ.get("FAKE_GOOGLE_PORT", "4799")
BASE = f"http://127.0.0.1:{PORT}"

# Démarre JARVIS avec l'OAuth redirigé vers le faux Google.
RUNNER = """
import sys
sys.path.insert(0, {repo!r})
import auth
auth.AUTH_URL = "http://127.0.0.1:{fake}/auth"
auth.TOKEN_URL = "http://127.0.0.1:{fake}/token"
auth.USERINFO_URL = "http://127.0.0.1:{fake}/userinfo"
import server
server.main()
"""

results: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'OK  ' if ok else 'FAIL'} {label:44} {detail}")
    results.append(bool(ok))


class Session:
    """Un navigateur distinct : son propre pot de cookies."""

    def __init__(self) -> None:
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, path: str) -> str:
        with self.opener.open(f"{BASE}{path}", timeout=5) as response:
            return response.read().decode("utf8")

    def json(self, path: str) -> dict:
        return json.loads(self.get(path))

    def login(self) -> None:
        with self.opener.open(f"{BASE}/auth/login", timeout=5) as response:
            response.read()

    def remember(self, text: str) -> None:
        request = urllib.request.Request(
            f"{BASE}/api/remember",
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener.open(request, timeout=5) as response:
            response.read()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-test-"))
    owner_notes = tmp / "owner-notes"
    owner_notes.mkdir(parents=True)
    (owner_notes / "carnet-prive.md").write_text(
        "# Carnet prive\n\nLe proprietaire prepare un projet confidentiel.\n", encoding="utf8")

    env = {k: v for k, v in os.environ.items() if not k.startswith("JARVIS_")}
    env.update(
        PORT=str(PORT),
        JARVIS_HOST="127.0.0.1",
        JARVIS_DATA_DIR=str(tmp / "data"),
        JARVIS_ACCESS_PATH=str(tmp / "access.json"),
        JARVIS_NOTES_DIR=str(owner_notes),
        JARVIS_PUBLIC_URL=BASE,
        JARVIS_GOOGLE_CLIENT_ID="test-client.apps.googleusercontent.com",
        JARVIS_GOOGLE_CLIENT_SECRET="test-secret",
        JARVIS_ALLOWED_EMAILS="moi@example.com, anna@example.com",
        JARVIS_ADMIN_EMAIL="moi@example.com",
    )

    fake = subprocess.Popen(
        [sys.executable, str(TESTS / "fake_google.py")],
        env=dict(os.environ, FAKE_GOOGLE_PORT=FAKE_PORT,
                 FAKE_EMAILS="moi@example.com,anna@example.com"),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)

    runner = tmp / "run_patched.py"
    runner.write_text(RUNNER.format(repo=str(REPO), fake=FAKE_PORT), encoding="utf8")
    server = subprocess.Popen(
        [sys.executable, "-u", str(runner)], cwd=REPO, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def wait_up() -> bool:
        for _ in range(80):
            try:
                urllib.request.urlopen(f"{BASE}/api/session", timeout=1)
                return True
            except urllib.error.HTTPError:
                return True
            except Exception:
                time.sleep(0.2)
        return False

    try:
        if not wait_up():
            print("FAIL le serveur n'a pas démarré")
            return 1

        me, anna = Session(), Session()
        me.login()
        anna.login()

        me_session = me.json("/api/session")
        anna_session = anna.json("/api/session")
        check("propriétaire connecté", me_session.get("email") == "moi@example.com", str(me_session.get("email")))
        check("invité connecté", anna_session.get("email") == "anna@example.com", str(anna_session.get("email")))
        check("propriétaire administrateur", me_session.get("isAdmin") is True)
        check("invité non administrateur", anna_session.get("isAdmin") is False)

        check("propriétaire : sa note", me.json("/api/status")["noteCount"] == 1)
        check("invité : son accueil seul", anna.json("/api/status")["noteCount"] == 1)

        me_graph = me.get("/graph-data.js")
        anna_graph = anna.get("/graph-data.js")
        check("graphe propriétaire : son carnet", "Carnet prive" in me_graph)
        check("graphe invité : aucune fuite",
              "Carnet prive" not in anna_graph and "confidentiel" not in anna_graph)
        check("graphe invité : son accueil", "Bienvenue" in anna_graph)

        anna.remember("Souviens-toi que Anna adore le piano")
        check("souvenir d'Anna invisible chez moi", "piano" not in me.get("/graph-data.js").lower())
        check("souvenir d'Anna bien chez elle", "piano" in anna.get("/graph-data.js").lower())
        check("compteurs distincts",
              me.json("/api/status")["noteCount"] == 1 and anna.json("/api/status")["noteCount"] == 2)

        access_me = me.json("/api/access")
        access_anna = anna.json("/api/access")
        check("admin : voit les deux comptes", access_me.get("count") == 2, str(access_me.get("count")))
        check("invité : ne voit que sa fiche",
              access_anna.get("count") == 1 and access_anna.get("admin") == "", str(access_anna.get("count")))

        anna_settings = anna.json("/api/settings")
        check("invité : chemin serveur masqué", anna_settings.get("notesDirResolved") == "")
        check("invité : espace personnel signalé", anna_settings.get("personalSpace") is True)

        owner_files = {p.name for p in owner_notes.rglob("*.md")}
        guest_files = {p.name for d in (tmp / "data" / "users").iterdir() for p in d.rglob("*.md")}
        check("disque : dossiers séparés", not (owner_files & guest_files),
              f"{len(owner_files)} vs {len(guest_files)}")
    finally:
        for proc in (server, fake):
            proc.terminate()
        for proc in (server, fake):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"{sum(results)}/{len(results)} vérifications passées")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
