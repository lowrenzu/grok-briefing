"""Préférences d'affichage par compte : nom et teinte.

Elles sont personnelles, pas globales : Anna peut appeler son JARVIS autrement et
le teinter en prune sans que cela change quoi que ce soit chez quiconque. Le
stockage suit la même règle que les notes — un fichier par compte, nommé par une
empreinte de l'adresse, donc aucune adresse en clair sur le disque.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

import workspaces as workspaces_module

DEFAULT_NAME = "JARVIS"
NAME_MAX_LENGTH = 24
ACCENTS = ("", "violet", "ambre", "prune")

# Lettres, chiffres, espaces, apostrophes et quelques signes : de quoi écrire
# « Jarvis », « Cortex », « Mon Œil » ou « J.A.R.V.I.S. » sans surprise.
_NAME_ALLOWED = re.compile(r"^[\w .'’\-]+$", re.UNICODE)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class PrefError(ValueError):
    """Préférence refusée, avec un message affichable tel quel."""


def clean_name(value: Any) -> str:
    """Nom affiché : vide = nom par défaut."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise PrefError("Le nom doit être du texte.")
    name = _CONTROL.sub("", value).strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        return ""
    if len(name) > NAME_MAX_LENGTH:
        raise PrefError(f"Le nom ne peut pas dépasser {NAME_MAX_LENGTH} caractères.")
    if not _NAME_ALLOWED.fullmatch(name):
        raise PrefError("Le nom ne peut contenir que des lettres, des chiffres, des espaces et . ' -")
    return name


def clean_accent(value: Any) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise PrefError("Teinte invalide.")
    accent = value.strip().casefold()
    if accent not in ACCENTS:
        raise PrefError("Teinte inconnue.")
    return accent


class Preferences:
    """Un fichier de préférences par compte, écrit atomiquement en 0600."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._lock = threading.RLock()
        self._cache: dict[str, dict[str, str]] = {}

    def _path(self, actor: str) -> Path:
        return self.root / f"{workspaces_module.slug_for(actor)}.json"

    def read(self, actor: str) -> dict[str, str]:
        """Préférences enregistrées, ou les valeurs par défaut."""
        if not workspaces_module.actor_is_valid(actor):
            return {"name": "", "accent": ""}
        with self._lock:
            cached = self._cache.get(actor)
            if cached is not None:
                return dict(cached)
            values = {"name": "", "accent": ""}
            path = self._path(actor)
            if path.is_file():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        try:
                            values["name"] = clean_name(raw.get("name"))
                            values["accent"] = clean_accent(raw.get("accent"))
                        except PrefError:
                            values = {"name": "", "accent": ""}
                except (OSError, json.JSONDecodeError):
                    values = {"name": "", "accent": ""}
            self._cache[actor] = values
            return dict(values)

    def write(self, actor: str, changes: dict[str, Any]) -> dict[str, str]:
        """Met à jour nom et/ou teinte de ce compte uniquement."""
        if not workspaces_module.actor_is_valid(actor):
            raise PrefError("Compte inconnu.")
        with self._lock:
            values = self.read(actor)
            if "name" in changes:
                values["name"] = clean_name(changes.get("name"))
            if "accent" in changes:
                values["accent"] = clean_accent(changes.get("accent"))

            self.root.mkdir(parents=True, exist_ok=True)
            path = self._path(actor)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            os.chmod(temporary, 0o600)
            temporary.replace(path)
            self._cache[actor] = dict(values)
            return dict(values)

    def public(self, actor: str) -> dict[str, Any]:
        """Vue envoyée au navigateur : le nom effectif, jamais le chemin."""
        values = self.read(actor)
        return {
            "name": values["name"] or DEFAULT_NAME,
            "customName": bool(values["name"]),
            "accent": values["accent"],
            "defaultName": DEFAULT_NAME,
            "maxLength": NAME_MAX_LENGTH,
            "accents": [item for item in ACCENTS if item],
        }
