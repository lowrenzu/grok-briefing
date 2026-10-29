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


# --- Icône du compte -------------------------------------------------------
# Un SVG plutôt qu'une image : net à toutes les tailles, et aucune dépendance
# de dessin côté serveur. Le navigateur peut l'utiliser comme icône installée.
ACCENT_PALETTE = {
    "":      {"core": "#7de7f5", "edge": "#3dc9e7", "glow": "#d8feff"},
    "violet": {"core": "#c9a8ff", "edge": "#8c6ee1", "glow": "#ece2ff"},
    "ambre":  {"core": "#f0c987", "edge": "#cda55f", "glow": "#fff3d6"},
    "prune":  {"core": "#d79ad0", "edge": "#a568a2", "glow": "#f7daf4"},
}


def initials(name: str, default: str = DEFAULT_NAME) -> str:
    """Une à deux lettres pour l'icône : « Cortex » → « C », « Mon Œil » → « MŒ »."""
    source = (name or default).strip() or default
    words = [w for w in source.split() if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    word = words[0]
    return word[:1].upper() if len(word) == 1 else word[:1].upper()


def icon_svg(name: str, accent: str) -> str:
    """Icône carrée : anneau lumineux et initiale du nom."""
    colors = ACCENT_PALETTE.get(accent, ACCENT_PALETTE[""])
    letters = initials(name)
    size = 512
    centre = size / 2
    # Deux lettres demandent une taille de police plus modeste.
    font = 210 if len(letters) == 1 else 150
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" role="img" aria-label="{xml_escape(name or DEFAULT_NAME)}">
  <defs>
    <radialGradient id="halo" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{colors['glow']}" stop-opacity=".55"/>
      <stop offset="55%" stop-color="{colors['core']}" stop-opacity=".18"/>
      <stop offset="100%" stop-color="{colors['core']}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="{size}" height="{size}" fill="#070b12"/>
  <circle cx="{centre}" cy="{centre}" r="196" fill="url(#halo)"/>
  <circle cx="{centre}" cy="{centre}" r="186" fill="none" stroke="{colors['edge']}" stroke-width="10" stroke-opacity=".85"/>
  <circle cx="{centre}" cy="{centre}" r="160" fill="none" stroke="{colors['core']}" stroke-width="3" stroke-opacity=".55"/>
  <circle cx="{centre}" cy="{centre}" r="206" fill="none" stroke="{colors['core']}" stroke-width="2" stroke-opacity=".22"/>
  <text x="{centre}" y="{centre}" text-anchor="middle" dominant-baseline="central"
        font-family="Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
        font-size="{font}" font-weight="600" letter-spacing="4"
        fill="{colors['glow']}">{xml_escape(letters)}</text>
</svg>
"""


def xml_escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;").replace('"', "&quot;"))
