#!/usr/bin/env python3
"""Génère les calques lumineux (yeux, bouche) alignés sur jarvis-hologram.png.

Les trois images partagent le même cadre 1376×768 (exporté en 2×) : affichées avec
le même `object-fit: cover`, elles restent alignées quel que soit l'écran.

Prérequis (hors exécution de l'application) : Pillow et numpy.
    python3 tools/build-hologram-lights.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "viewer" / "assets"
FRAME = (1376, 768)
SCALE = 2  # le portrait est exporté en 2×
LIGHT_SCALE = 1  # les halos sont doux : 1× suffit et économise la mémoire GPU


def gaussian_layer(width: int, height: int, blobs: list[tuple[float, float, float, float, float]]) -> np.ndarray:
    """Somme de taches gaussiennes (x, y, sigma_x, sigma_y, intensité) en 0..1."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    field = np.zeros((height, width), dtype=np.float32)
    for x, y, sigma_x, sigma_y, strength in blobs:
        field += strength * np.exp(
            -0.5 * (((xx - x) / sigma_x) ** 2 + ((yy - y) / sigma_y) ** 2)
        )
    return np.clip(field, 0.0, 1.0)


def tint(mask: np.ndarray, colour: tuple[int, int, int]) -> Image.Image:
    height, width = mask.shape
    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2] = colour
    alpha = mask * 255.0
    return Image.fromarray(np.dstack([rgb, alpha.astype(np.uint8)]), "RGBA")


def main() -> None:
    hologram = Image.open(ASSETS / "jarvis-hologram.png").convert("RGBA")
    if hologram.size != (FRAME[0] * SCALE, FRAME[1] * SCALE):
        raise SystemExit(f"jarvis-hologram.png doit mesurer {FRAME[0] * SCALE}×{FRAME[1] * SCALE}")
    width, height = FRAME[0] * LIGHT_SCALE, FRAME[1] * LIGHT_SCALE
    silhouette = np.asarray(
        hologram.getchannel("A").resize((width, height), Image.Resampling.LANCZOS),
        dtype=np.float32,
    ) / 255.0

    def px(value: float) -> float:
        return value * LIGHT_SCALE

    # Repères relevés sur le portrait : yeux à 47,1 % / 53,05 % de largeur, bouche à 50 %.
    eye_y = px(239)
    blobs_eyes = []
    for eye_x in (px(648), px(730)):
        blobs_eyes.extend([
            (eye_x, eye_y, px(21), px(6.5), 1.0),
            (eye_x, eye_y, px(12), px(3.4), .55),
        ])
    eyes = tint(gaussian_layer(width, height, blobs_eyes), (214, 250, 255))

    mouth_x, mouth_y = px(689), px(330)
    blobs_voice = [
        (mouth_x, mouth_y, px(30), px(9), .85),
        (mouth_x, mouth_y + px(26), px(40), px(20), .5),
        (mouth_x, mouth_y + px(74), px(52), px(34), .28),
    ]
    voice = tint(gaussian_layer(width, height, blobs_voice), (150, 240, 255))

    for image, name in ((eyes, "jarvis-eyes-glow.png"), (voice, "jarvis-voice-glow.png")):
        data = np.asarray(image, dtype=np.float32)
        data[:, :, 3] *= silhouette  # la lumière ne déborde jamais de la silhouette
        merged = Image.fromarray(data.astype(np.uint8), "RGBA")
        destination = ASSETS / name
        merged.save(destination, optimize=True)
        print(f"{name}: {destination.stat().st_size:,} octets · bbox {merged.getchannel('A').getbbox()}")


if __name__ == "__main__":
    main()
