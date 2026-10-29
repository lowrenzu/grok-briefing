"""Faux service de voix neuronale : aucun réseau, aucun son.

Il imite `edge_tts.Communicate` et note chaque appel dans un fichier, ce qui
permet de vérifier le texte réellement envoyé et l'efficacité du cache.

`FAKE_EDGE_TTS_PANNE` : si ce chemin existe, la synthèse échoue — comme un
ordinateur hors ligne.
"""
import os
from pathlib import Path

APPELS = Path(os.environ["FAKE_EDGE_TTS_COMPTE"])
PANNE = os.environ.get("FAKE_EDGE_TTS_PANNE")


class Communicate:
    def __init__(self, texte, voix, **options):
        self.texte = texte
        self.voix = voix
        self.options = options

    async def stream(self):
        if PANNE and Path(PANNE).exists():
            raise RuntimeError("service de synthèse indisponible")
        with APPELS.open("a", encoding="utf8") as journal:
            journal.write(f"{self.voix}\t{self.texte}\n")
        yield {"type": "audio", "data": b"ID3FAKE" + self.texte.encode("utf8")}
        yield {"type": "WordBoundary", "data": b""}
