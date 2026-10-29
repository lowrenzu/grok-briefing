"""Voix neuronale française pour JARVIS.

Les voix incluses dans Windows datent des années 2000 : elles nasillent. Ce
module utilise les voix neuronales de Microsoft (les mêmes que la lecture à voix
haute d'Edge), qui ne demandent ni clé, ni compte, ni réglage.

Si le paquet `edge-tts` n'est pas installé, ou si l'ordinateur est hors ligne,
`synthese()` renvoie `None` : l'interface reprend alors la voix du navigateur.
Rien ne casse, rien n'est bloqué.
"""
from __future__ import annotations

import asyncio
import importlib.util
import threading
import unicodedata

MAX_CARACTERES = 900
DELAI_MAXIMUM = 14.0

# La voix d'usine : masculine et posée, cohérente avec « monsieur ».
VOIX_PAR_DEFAUT = "fr-FR-HenriNeural"

VOIX_DISPONIBLES = {
    "Henri": "fr-FR-HenriNeural",
    "Denise": "fr-FR-DeniseNeural",
    "Rémy": "fr-FR-RemyMultilingualNeural",
    "Vivienne": "fr-FR-VivienneMultilingualNeural",
}

_cache: dict[tuple[str, str], bytes] = {}
_cache_lock = threading.Lock()
MAX_CACHE = 40


def paquet_present() -> bool:
    """Vrai si edge-tts est installé. Aucun import n'est tenté ici."""
    try:
        return importlib.util.find_spec("edge_tts") is not None
    except (ImportError, ValueError):
        return False


def disponible() -> bool:
    return paquet_present()


def nettoyer(texte: str) -> str:
    """Retire ce qui se lirait mal : retours à la ligne, symboles, espaces fous."""
    texte = unicodedata.normalize("NFC", str(texte or ""))
    texte = " ".join(texte.replace("\u00a0", " ").split())
    return texte[:MAX_CARACTERES].strip()


def _lire(texte: str, voix: str) -> bytes:
    """Appelle le service de synthèse et rapporte les octets audio (MP3)."""
    import edge_tts  # importé ici : le module reste utilisable sans le paquet

    async def collecter() -> bytes:
        communication = edge_tts.Communicate(texte, voix)
        morceaux = bytearray()
        async for evenement in communication.stream():
            if evenement.get("type") == "audio" and evenement.get("data"):
                morceaux.extend(evenement["data"])
        return bytes(morceaux)

    return asyncio.run(asyncio.wait_for(collecter(), timeout=DELAI_MAXIMUM))


def synthese(texte: str, voix: str | None = None) -> bytes | None:
    """Audio MP3 de la phrase, ou None si la voix neuronale est indisponible."""
    phrase = nettoyer(texte)
    if not phrase:
        return None
    if voix not in VOIX_DISPONIBLES.values():
        voix = VOIX_PAR_DEFAUT
    cle = (voix, phrase)
    with _cache_lock:
        if cle in _cache:
            return _cache[cle]
    if not paquet_present():
        return None
    try:
        audio = _lire(phrase, cle[0])
    except Exception as exc:  # hors ligne, service indisponible, quota…
        print(f"[JARVIS] Voix neuronale indisponible : {type(exc).__name__}")
        return None
    if not audio:
        return None
    with _cache_lock:
        if len(_cache) >= MAX_CACHE:
            _cache.pop(next(iter(_cache)))
        _cache[cle] = audio
    return audio


def etat() -> dict[str, object]:
    """Ce que l'interface a besoin de savoir pour choisir sa voix."""
    return {
        "neural": paquet_present(),
        "voice": VOIX_PAR_DEFAUT,
        "voices": [{"label": nom, "id": identifiant} for nom, identifiant in VOIX_DISPONIBLES.items()],
        "fallback": "navigateur",
    }
