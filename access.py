#!/usr/bin/env python3
"""Liste d'accès de JARVIS : qui a le droit d'entrer, et qui administre.

Google vérifie l'identité ; ce fichier décide de l'autorisation. Il contient
uniquement des adresses e-mail (aucun mot de passe, aucun jeton) et vit dans
`access.json`, lisible par le seul propriétaire du serveur (droits 600).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Iterable

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}")
MAX_EMAILS = 20


class AccessError(ValueError):
    """Message destiné à l'utilisateur (affiché tel quel dans le panneau)."""


def normalize_email(value: str) -> str:
    email = str(value or "").strip().casefold()
    if not email:
        raise AccessError("Indiquez une adresse e-mail.")
    if not EMAIL_PATTERN.fullmatch(email):
        raise AccessError("Cette adresse e-mail ne semble pas valide.")
    return email


class AccessList:
    """Adresses autorisées + administrateur, persistées dans access.json."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.admin = ""
        self._people: dict[str, dict[str, Any]] = {}
        self.reload()

    # --- lecture ----------------------------------------------------------
    def reload(self) -> None:
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            admin = str((data or {}).get("admin") or "").strip().casefold()
            people: dict[str, dict[str, Any]] = {}
            for entry in (data or {}).get("emails") or []:
                if isinstance(entry, str):
                    email, added, seen, note = entry.casefold(), 0.0, 0.0, ""
                elif isinstance(entry, dict):
                    email = str(entry.get("email") or "").casefold().strip()
                    added = float(entry.get("added") or 0)
                    seen = float(entry.get("last_seen") or 0)
                    note = str(entry.get("note") or "")
                else:
                    continue
                if email and EMAIL_PATTERN.fullmatch(email):
                    people[email] = {"email": email, "added": added, "last_seen": seen, "note": note}
            with self._lock:
                self.admin = admin if admin in people else (next(iter(people), ""))
                self._people = people
        else:
            with self._lock:
                self.admin = ""
                self._people = {}

    def seed(self, emails: Iterable[str] | str, admin: str = "") -> None:
        """Première initialisation depuis config.json (aucun fichier encore écrit)."""
        if self.path.is_file():
            return
        if isinstance(emails, str):
            # « a@x.fr, b@y.fr » ou « a@x.fr; b@y.fr »
            emails = [item.strip() for item in emails.replace(";", ",").split(",")]
        # Nettoyage tolérant : guillemets de copier-coller, espaces, retours à la ligne.
        people = [item for item in (str(email).strip().strip("'\"") for email in emails) if item]
        if not people:
            print("[JARVIS] Aucune adresse autorisée fournie : personne ne pourra entrer.")
            return
        with self._lock:
            now = time.time()
            for raw in people:
                try:
                    email = normalize_email(raw)
                except AccessError:
                    print(f"[JARVIS] Adresse ignorée (format invalide) : {raw!r}")
                    continue
                self._people[email] = {"email": email, "added": now, "last_seen": 0.0, "note": ""}
            wanted = str(admin or "").strip().casefold()
            self.admin = wanted if wanted in self._people else next(iter(self._people), "")
            self._save()

    @property
    def emails(self) -> set[str]:
        with self._lock:
            return set(self._people)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._people)

    def allows(self, email: str) -> bool:
        with self._lock:
            return str(email or "").casefold() in self._people

    def is_admin(self, email: str | None) -> bool:
        with self._lock:
            return bool(email) and str(email).casefold() == self.admin

    def public(self, viewer: str | None = None) -> dict[str, Any]:
        viewer = (viewer or "").casefold()
        with self._lock:
            people = []
            for email, person in sorted(self._people.items(), key=lambda item: item[1].get("added") or 0):
                people.append({
                    "email": email,
                    "added": person.get("added") or 0,
                    "lastSeen": person.get("last_seen") or 0,
                    "isAdmin": email == self.admin,
                    "isYou": email == viewer,
                })
            return {
                "admin": self.admin,
                "emails": people,
                "count": len(people),
                "max": MAX_EMAILS,
                "viewerIsAdmin": bool(viewer) and viewer == self.admin,
            }

    # --- écriture ---------------------------------------------------------
    def add(self, email: str, note: str = "") -> str:
        clean = normalize_email(email)
        with self._lock:
            if clean in self._people:
                raise AccessError("Cette adresse a déjà accès.")
            if len(self._people) >= MAX_EMAILS:
                raise AccessError(f"Limite atteinte ({MAX_EMAILS} adresses).")
            self._people[clean] = {"email": clean, "added": time.time(), "last_seen": 0.0, "note": note.strip()[:80]}
            if not self.admin:
                self.admin = clean
            self._save()
        return clean

    def remove(self, email: str) -> str:
        clean = normalize_email(email)
        with self._lock:
            if clean not in self._people:
                raise AccessError("Cette adresse n’a pas accès.")
            if clean == self.admin:
                raise AccessError("Impossible de retirer le compte administrateur. Désignez un autre administrateur d’abord.")
            if len(self._people) <= 1:
                raise AccessError("Gardez au moins une adresse : sinon plus personne ne pourra entrer.")
            self._people.pop(clean)
            self._save()
        return clean

    def note_login(self, email: str) -> None:
        clean = str(email or "").casefold()
        with self._lock:
            person = self._people.get(clean)
            if not person:
                return
            person["last_seen"] = time.time()
            self._save()

    def _save(self) -> None:
        data = {
            "admin": self.admin,
            "emails": [
                {
                    "email": person["email"],
                    "added": person.get("added") or 0,
                    "last_seen": person.get("last_seen") or 0,
                    **({"note": person["note"]} if person.get("note") else {}),
                }
                for person in sorted(self._people.values(), key=lambda item: item.get("added") or 0)
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(self.path.parent), prefix=".access-", suffix=".json", delete=False
        )
        try:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.chmod(handle.name, 0o600)
        os.replace(handle.name, self.path)
