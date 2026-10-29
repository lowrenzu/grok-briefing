"""Premier réglage de JARVIS, sans confier les identifiants à personne.

Le serveur démarre volontairement sans identifiants Google. Il fabrique alors un
**code d'installation** court, écrit dans un fichier privé et affiché une seule
fois dans son journal. Ce code sert à ouvrir `/setup` depuis un navigateur, où
la personne colle elle-même son ID client, son code secret et son adresse.

Le code ne vaut qu'une fois, et la page disparaît dès que la configuration est
écrite : `/setup` répond ensuite « déjà configuré ».
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
from pathlib import Path
from typing import Any

TOKEN_FILE = "setup-token.txt"
# 8 caractères hexadécimaux : court à recopier depuis un journal, mais
# 4 milliards de possibilités et cinq essais seulement (voir MAX_ATTEMPTS).
TOKEN_LENGTH = 8
MAX_ATTEMPTS = 5

EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
CLIENT_ID_PATTERN = re.compile(r"^[0-9]+-[A-Za-z0-9_\-]{10,}\.apps\.googleusercontent\.com$")


class SetupError(RuntimeError):
    """Message destiné à être affiché tel quel."""


def clean_client_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise SetupError("L’ID client est vide.")
    if not CLIENT_ID_PATTERN.fullmatch(text):
        raise SetupError(
            "L’ID client ne ressemble pas à un identifiant Google : "
            "il doit finir par « .apps.googleusercontent.com »."
        )
    return text


def clean_client_secret(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise SetupError("Le code secret est vide.")
    if len(text) < 20:
        raise SetupError("Le code secret semble incomplet : recopiez-le en entier.")
    return text


def clean_email(value: Any) -> str:
    text = str(value or "").strip().strip("'\"").casefold()
    if not EMAIL_PATTERN.fullmatch(text):
        raise SetupError("L’adresse e-mail n’est pas valide.")
    return text


class Setup:
    """État du premier réglage : code d'installation et écriture de config.json."""

    def __init__(self, data_dir: Path, config_path: Path) -> None:
        self.data_dir = data_dir
        self.config_path = config_path
        self.token_path = data_dir / TOKEN_FILE
        self._lock = threading.RLock()
        self._attempts = 0

    # --- état -------------------------------------------------------------
    def pending(self) -> bool:
        """Vrai tant qu'aucun identifiant Google n'est enregistré."""
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return True
        block = data.get("auth") if isinstance(data.get("auth"), dict) else {}
        return not (block.get("google_client_id") and block.get("google_client_secret"))

    # --- code d'installation ---------------------------------------------
    def token(self) -> str:
        """Lit le code existant, ou en fabrique un (fichier privé 0600)."""
        with self._lock:
            try:
                existant = self.token_path.read_text(encoding="utf-8").strip()
                if len(existant) >= TOKEN_LENGTH:
                    return existant
            except OSError:
                pass
            code = secrets.token_hex(TOKEN_LENGTH // 2)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(code + "\n", encoding="utf-8")
            try:
                os.chmod(self.token_path, 0o600)
            except OSError:
                pass
            return code

    def forget_token(self) -> None:
        with self._lock:
            try:
                self.token_path.unlink()
            except OSError:
                pass

    def check_token(self, value: Any) -> bool:
        """Compare le code présenté. Cinq essais ratés ferment la page."""
        with self._lock:
            if self._attempts >= MAX_ATTEMPTS:
                raise SetupError(
                    "Trop d’essais. Redémarrez le service pour obtenir un nouveau code."
                )
            attendu = self.token()
            fourni = str(value or "").strip()
            if fourni and secrets.compare_digest(fourni, attendu):
                self._attempts = 0
                return True
            self._attempts += 1
            return False

    # --- écriture ---------------------------------------------------------
    def apply(self, form: dict[str, Any], public_url: str) -> dict[str, Any]:
        """Valide et enregistre les identifiants. Renvoie le bloc `auth` écrit."""
        client_id = clean_client_id(form.get("client_id"))
        client_secret = clean_client_secret(form.get("client_secret"))
        admin = clean_email(form.get("admin_email"))

        existant: dict[str, Any] = {}
        try:
            lecture = json.loads(self.config_path.read_text(encoding="utf-8"))
            if isinstance(lecture, dict):
                existant = lecture
        except (OSError, json.JSONDecodeError):
            existant = {}

        existant["auth"] = {
            "google_client_id": client_id,
            "google_client_secret": client_secret,
            "allowed_emails": admin,
            "admin_email": admin,
            "public_url": public_url.rstrip("/"),
        }
        existant.setdefault("notes_dir", "examples/demo-notes")

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(existant, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        try:
            os.chmod(self.config_path, 0o600)
        except OSError:
            pass
        self.forget_token()
        return dict(existant["auth"])
