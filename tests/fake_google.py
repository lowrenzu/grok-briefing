"""Faux fournisseur OAuth, pour tester la connexion sans réseau ni vrais comptes.

Imite les trois points de Google utilisés par `auth.py` :

    GET  /auth      → redirige vers `redirect_uri` avec un code et le state
    POST /token     → échange le code contre un jeton d'accès
    GET  /userinfo  → renvoie l'adresse contenue dans le jeton

L'adresse est encodée dans le code, ce qui rend le parcours déterministe.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("FAKE_GOOGLE_PORT", "4799"))
EMAILS = [e.strip() for e in os.environ.get("FAKE_EMAILS", "moi@gmail.com").split(",") if e.strip()]
_count = {"n": 0}


def encode(email: str) -> str:
    return base64.urlsafe_b64encode(email.encode()).decode().rstrip("=")


def decode(value: str) -> str:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status: int, body: bytes, content_type: str = "application/json", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parts.query)

        if parts.path == "/auth":
            email = EMAILS[_count["n"] % len(EMAILS)]
            _count["n"] += 1
            redirect = (query.get("redirect_uri") or [""])[0]
            state = (query.get("state") or [""])[0]
            location = f"{redirect}?code=code-{encode(email)}&state={urllib.parse.quote(state)}"
            self._send(302, b"", "text/plain", {"Location": location})
            return

        if parts.path == "/userinfo":
            token = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if not token.startswith("access-"):
                self._send(401, b"{}")
                return
            email = decode(token[len("access-"):])
            body = json.dumps({"email": email, "email_verified": True,
                               "name": email.split("@")[0]}).encode()
            self._send(200, body)
            return

        self._send(404, b"{}")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        code = (form.get("code") or [""])[0]
        email = decode(code[len("code-"):]) if code.startswith("code-") else ""
        body = json.dumps({"access_token": f"access-{encode(email)}",
                           "token_type": "Bearer", "expires_in": 3600}).encode()
        self._send(200, body)


def main() -> None:
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
