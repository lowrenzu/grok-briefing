#!/usr/bin/env python3
"""Ouverture de session Google pour JARVIS.

Le serveur ne demande jamais votre mot de passe Google : il délègue la connexion à
Google (protocole OAuth 2.0 avec PKCE), reçoit un code à usage unique, l'échange
contre un jeton côté serveur, puis lit votre adresse e-mail sur l'API Google.
Si cette adresse figure dans `allowed_emails`, une session locale est créée.

Aucune dépendance : uniquement la bibliothèque standard.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPES = "openid email profile"

SESSION_TTL = 7 * 24 * 3600      # une semaine de session
STATE_TTL = 600                  # 10 minutes pour revenir de chez Google
COOKIE_NAME = "jarvis_auth"


class AuthError(RuntimeError):
    """Message destiné à l'utilisateur, affiché tel quel sur la page d'erreur."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class GoogleAuth:
    """État d'authentification d'un serveur JARVIS.

    `enabled` est vrai seulement si un identifiant et un secret Google sont fournis.
    Sans eux, JARVIS reste ouvert comme avant (utile en local, à éviter en ligne).
    """

    def __init__(self, client_id: str = "", client_secret: str = "", allowed: Any = "",
                 public_url: str = "") -> None:
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        # `allowed` peut être une liste, une chaîne séparée par des virgules, un
        # ensemble, ou une fonction : la liste d'accès pouvant changer en direct,
        # on accepte un fournisseur appelé à chaque vérification.
        self._allowed_source = allowed
        self.allowed = self._read_allowed(allowed)
        self.public_url = (public_url or "").strip().rstrip("/")
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._states: dict[str, dict[str, Any]] = {}

    # --- configuration ----------------------------------------------------
    @staticmethod
    def _read_allowed(source: Any) -> set[str]:
        if callable(source):
            source = source()
        if isinstance(source, str):
            source = [item.strip() for item in source.replace(";", ",").split(",")]
        return {str(item).strip().casefold() for item in (source or []) if str(item).strip()}

    def refresh(self) -> None:
        """Relit la source d'adresses autorisées (listes gérées ailleurs)."""
        self.allowed = self._read_allowed(self._allowed_source)

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def allows_anyone(self) -> bool:
        """Vrai si la liste d'adresses autorisées est vide : personne ne passe."""
        return not self.allowed

    @property
    def ready(self) -> bool:
        """Prêt à protéger l'accès : identifiants Google et au moins une adresse."""
        return self.enabled and not self.allows_anyone

    def redirect_uri(self, scheme: str, host: str) -> str:
        base = self.public_url or f"{scheme}://{host}"
        return f"{base.rstrip('/')}/auth/callback"

    def info(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "ready": self.ready,
            "allowedCount": len(self.allowed),
            "publicUrl": self.public_url,
        }

    # --- sessions ---------------------------------------------------------
    def new_session(self, email: str, name: str = "") -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._prune(now)
            self._sessions[token] = {"email": email, "name": name, "created": now, "last_seen": now}
        return token, cookie_value(token, SESSION_TTL)

    def session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        now = time.time()
        with self._lock:
            self._prune(now)
            found = self._sessions.get(token)
            if not found:
                return None
            found["last_seen"] = now
            return dict(found)

    def drop_email(self, email: str) -> int:
        """Ferme toutes les sessions d'une adresse (retrait d'accès)."""
        target = str(email or "").casefold()
        with self._lock:
            tokens = [key for key, value in self._sessions.items() if value["email"] == target]
            for key in tokens:
                self._sessions.pop(key, None)
        return len(tokens)

    def signed_in(self) -> dict[str, int]:
        """Nombre de sessions actives par adresse (utilisé par le panneau admin)."""
        with self._lock:
            totals: dict[str, int] = {}
            for value in self._sessions.values():
                totals[value["email"]] = totals.get(value["email"], 0) + 1
            return totals

    def drop_session(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def _prune(self, now: float) -> None:
        for token in [key for key, value in self._sessions.items() if now - value["last_seen"] > SESSION_TTL]:
            self._sessions.pop(token, None)
        for state in [key for key, value in self._states.items() if now - value["created"] > STATE_TTL]:
            self._states.pop(state, None)

    # --- allers-retours avec Google --------------------------------------
    def authorize_url(self, redirect_uri: str) -> str:
        if not self.enabled:
            raise AuthError("La connexion Google n’est pas configurée sur ce serveur.")
        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        challenge = _b64(hashlib.sha256(verifier.encode()).digest())
        with self._lock:
            self._prune(time.time())
            self._states[state] = {"verifier": verifier, "created": time.time(), "redirect_uri": redirect_uri}
        query = urllib.parse.urlencode({
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "online",
            "prompt": "select_account",
        })
        return f"{AUTH_URL}?{query}"

    def exchange(self, code: str, state: str) -> dict[str, Any]:
        """Vérifie le retour de Google et renvoie l'identité autorisée."""
        with self._lock:
            self._prune(time.time())
            pending = self._states.pop(state or "", None)
        if not pending:
            raise AuthError("La connexion a expiré ou la demande est invalide. Recommencez.")
        payload = urllib.parse.urlencode({
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": pending["redirect_uri"],
            "grant_type": "authorization_code",
            "code_verifier": pending["verifier"],
        }).encode()
        tokens = _post_form(TOKEN_URL, payload)
        access = tokens.get("access_token")
        if not access:
            raise AuthError("Google n’a pas renvoyé de jeton d’accès.")
        profile = _get_json(USERINFO_URL, {"Authorization": f"Bearer {access}"})
        email = str(profile.get("email") or "").strip().casefold()
        if not email:
            raise AuthError("Google n’a pas communiqué d’adresse e-mail.")
        if not profile.get("email_verified", False):
            raise AuthError("Cette adresse Google n’est pas vérifiée.")
        if email not in self.allowed:
            raise AuthError("Ce compte Google n’est pas autorisé sur ce JARVIS.")
        return {"email": email, "name": str(profile.get("name") or "")}


def _post_form(url: str, body: bytes) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return _json(response.read())
    except urllib.error.HTTPError as exc:
        # Le corps d'erreur de Google peut contenir des détails : on reste générique.
        detail = "code refusé" if exc.code == 400 else f"HTTP {exc.code}"
        raise AuthError(f"Google a refusé la connexion ({detail}).") from None
    except (urllib.error.URLError, TimeoutError):
        raise AuthError("Google est injoignable depuis ce serveur (réseau bloqué ?).") from None


def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return _json(response.read())
    except urllib.error.HTTPError as exc:
        raise AuthError(f"Google a refusé de lire le profil (HTTP {exc.code}).") from None
    except (urllib.error.URLError, TimeoutError):
        raise AuthError("Google est injoignable depuis ce serveur (réseau bloqué ?).") from None


def _json(raw: bytes) -> dict[str, Any]:
    import json

    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise AuthError("Google a renvoyé une réponse illisible.") from None
    return value if isinstance(value, dict) else {}


def cookie_value(token: str, max_age: int, secure: bool = False) -> str:
    parts = [f"{COOKIE_NAME}={token}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def cleared_cookie(secure: bool = False) -> str:
    parts = [f"{COOKIE_NAME}=", "Path=/", "HttpOnly", "SameSite=Lax", "Max-Age=0"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def from_environment() -> GoogleAuth:
    """Lit la configuration Google (variables d'environnement prioritaires)."""
    return GoogleAuth(
        client_id=os.environ.get("JARVIS_GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("JARVIS_GOOGLE_CLIENT_SECRET", ""),
        allowed=os.environ.get("JARVIS_ALLOWED_EMAILS", ""),
        public_url=os.environ.get("JARVIS_PUBLIC_URL", ""),
    )
