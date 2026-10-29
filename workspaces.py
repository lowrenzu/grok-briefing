"""Un espace de notes par compte : chacun son JARVIS, aucun mélange.

Le propriétaire (le compte administrateur de `access.json`) garde le dossier de
notes configuré depuis le début. Tout autre compte autorisé reçoit, à sa première
connexion, un dossier personnel :

    <racine des données>/users/<empreinte-de-l-adresse>/notes/

L'empreinte est un hachage : le disque ne révèle pas les adresses e-mail, et deux
adresses différentes ne peuvent pas se retrouver dans le même dossier.
"""

from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path
from typing import Any

# Identité utilisée quand la porte Google est ouverte (développement local).
LOCAL_ACTOR = "__local__"

_SAFE = re.compile(r"[^a-z0-9]+")

WELCOME_TITLE = "Bienvenue dans ton JARVIS"
WELCOME_BODY = """# {title}

Cet espace est **le tien**. Personne d'autre n'y a accès : ni les autres comptes
autorisés, ni l'administrateur du serveur ne voient ces notes depuis JARVIS.

## Par où commencer

- **Écris ta première note** : dis simplement à JARVIS
  « Souviens-toi que… » et il créera l'étoile correspondante.
- **Ajoute des fichiers** : dépose des notes Markdown dans ce dossier, elles
  apparaîtront dans la galaxie au prochain chargement.
- **Explore** : chaque note devient une étoile, les liens entre elles dessinent
  les constellations.

## À savoir

- Les réglages du cerveau (fournisseur d'IA) sont communs à l'installation :
  c'est l'administrateur qui les configure.
- Ta liste de notes, ton graphe et ta mémoire sont strictement séparés.
"""


def slug_for(actor: str) -> str:
    """Nom de dossier stable, sans l'adresse en clair."""
    if actor == LOCAL_ACTOR:
        return "local"
    digest = hashlib.sha256(actor.strip().casefold().encode("utf-8")).hexdigest()
    return digest[:24]


def actor_is_valid(actor: str) -> bool:
    return bool(actor) and len(actor) <= 200 and "\x00" not in actor


class Workspaces:
    """Résout le dossier de notes de chaque compte, et le crée au besoin."""

    def __init__(self, root: str | Path, owner_notes: str | Path, owner_email: str = "") -> None:
        self.root = Path(root)
        self.owner_notes = Path(owner_notes)
        self._owner_email = (owner_email or "").strip().casefold()
        self._lock = threading.RLock()
        self._ready: set[str] = set()

    # --- propriétaire ------------------------------------------------------
    def set_owner(self, email: str) -> None:
        with self._lock:
            self._owner_email = (email or "").strip().casefold()

    def is_owner(self, actor: str) -> bool:
        """Le propriétaire garde le dossier historique ; lui seul partage son espace."""
        if actor == LOCAL_ACTOR:
            return True
        if not self._owner_email:
            return False
        return actor.strip().casefold() == self._owner_email

    # --- chemins -----------------------------------------------------------
    def dir_for(self, actor: str) -> Path:
        if not actor_is_valid(actor):
            raise ValueError("Compte inconnu.")
        if self.is_owner(actor):
            return self.owner_notes
        return self.root / "users" / slug_for(actor) / "notes"

    def notes_dir(self, actor: str) -> Path:
        """Dossier de notes du compte ; créé et accueilli à la première visite."""
        path = self.dir_for(actor)
        if self.is_owner(actor):
            return path
        with self._lock:
            if actor in self._ready:
                return path
            if not path.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                (path / "bienvenue.md").write_text(
                    WELCOME_BODY.format(title=WELCOME_TITLE), encoding="utf-8"
                )
            self._ready.add(actor)
            return path

    # --- diagnostic --------------------------------------------------------
    def summary(self, actor: str) -> dict[str, Any]:
        return {
            "actor": actor,
            "owner": self.is_owner(actor),
            "dir": str(self.dir_for(actor)),
        }
