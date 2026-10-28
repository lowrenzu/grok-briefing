#!/usr/bin/env python3
"""Compose le cœur holographique de JARVIS : quatre anneaux concentriques animés.

Couches produites (PNG RGBA carrés, centrés, 608 px de côté) :

1. `jarvis-core-ring.png`   — couronne métallique sombre (le cerclage)
2. `jarvis-core-veil.png`   — anneau de verre strié (la couronne interne)
3. `jarvis-core-disc.png`   — disque HUD cyan et ses graduations
4. `jarvis-core-light.png`  — orbe lumineuse centrale

Les sources de `tools/sources/` sont des images générées sur fond noir ou damier :
le fond est estimé puis retiré, l'alpha est déduit de l'éclat et de la saturation.

    python3 tools/build-jarvis-core.py            # écrit les quatre calques
    python3 tools/build-jarvis-core.py --preview  # + rendus de contrôle repos/parole

Prérequis (uniquement pour cette commande) : Pillow et numpy.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "viewer" / "assets"
SOURCES = ROOT / "tools" / "sources"
EXPORT = 608  # 1,6× le diamètre CSS de 380 px : net sur écran Retina


def load(name: str) -> np.ndarray:
    return np.asarray(Image.open(SOURCES / name).convert("RGB"), dtype=np.float32) / 255.0


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb.max(axis=2)


def chroma(rgb: np.ndarray) -> np.ndarray:
    return rgb.max(axis=2) - rgb.min(axis=2)


def smoothstep(field: np.ndarray, low: float, high: float) -> np.ndarray:
    x = np.clip((field - low) / max(high - low, 1e-6), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def feather(alpha: np.ndarray, radius: float = 1.2) -> np.ndarray:
    image = Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8), "L")
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32) / 255.0


def remove_backdrop(rgb: np.ndarray, strength: float = 1.30) -> np.ndarray:
    """Retire l'ombre portée d'un fond noir en estimant la valeur des bords."""
    border = np.concatenate([
        rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3),
        rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3),
    ])
    backdrop = np.median(border, axis=0)
    scale = max(1.0 - float(backdrop.max()) * strength, 0.35)
    return np.clip((rgb - backdrop * strength) / scale, 0, 1)


def crop_to_content(rgb: np.ndarray, alpha: np.ndarray, threshold: float = 0.02) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.where(alpha > threshold)
    if not len(xs):
        raise SystemExit("Source vide : vérifiez tools/sources/.")
    box = (ys.min(), ys.max() + 1, xs.min(), xs.max() + 1)
    return rgb[box[0]:box[1], box[2]:box[3]], alpha[box[0]:box[1], box[2]:box[3]]


def square(rgb: np.ndarray, alpha: np.ndarray, fill: float = 0.92) -> tuple[np.ndarray, np.ndarray]:
    """Centre la découpe dans un carré : `fill` = part du carré occupée par l'anneau."""
    height, width = alpha.shape
    side = int(round(max(height, width) / max(fill, 0.05)))
    canvas_rgb = np.zeros((side, side, 3), dtype=np.float32)
    canvas_alpha = np.zeros((side, side), dtype=np.float32)
    top, left = (side - height) // 2, (side - width) // 2
    canvas_rgb[top:top + height, left:left + width] = rgb
    canvas_alpha[top:top + height, left:left + width] = alpha
    return canvas_rgb, canvas_alpha


def resize(rgb: np.ndarray, alpha: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray]:
    """Redimensionnement prémultiplié : pas de liseré sombre autour des reflets."""
    premultiplied = np.dstack([rgb * alpha[:, :, None], alpha]) * 255.0
    image = Image.fromarray(premultiplied.clip(0, 255).astype(np.uint8), "RGBA")
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    data = np.asarray(image, dtype=np.float32) / 255.0
    out_alpha = data[:, :, 3]
    out_rgb = np.divide(data[:, :, :3], np.maximum(out_alpha, 1e-4)[:, :, None])
    return np.clip(out_rgb, 0, 1), np.clip(out_alpha, 0, 1)


def save(rgb: np.ndarray, alpha: np.ndarray, name: str) -> None:
    data = np.dstack([rgb * 255.0, alpha * 255.0]).clip(0, 255).astype(np.uint8)
    image = Image.fromarray(data, "RGBA").resize((EXPORT, EXPORT), Image.Resampling.LANCZOS)
    destination = ASSETS / name
    image.save(destination, optimize=True)
    print(f"{name:26s} {destination.stat().st_size:>8,} octets  bbox {image.getchannel('A').getbbox()}")


def steel_colour(rgb: np.ndarray, dark: str, light: str) -> np.ndarray:
    """Acier bleuté : l'éclat d'origine module un dégradé sombre → clair contrôlé.

    Recolorer avec des teintes fixes évite les verts olive qu'un simple produit
    chroma/luminance fait apparaître sur des pixels presque noirs.
    """
    low = np.array([int(dark[index:index + 2], 16) / 255 for index in (1, 3, 5)], dtype=np.float32)
    high = np.array([int(light[index:index + 2], 16) / 255 for index in (1, 3, 5)], dtype=np.float32)
    lum = luminance(rgb)
    reference = max(float(np.percentile(lum[lum > 0.02], 99.5)) if (lum > 0.02).any() else 0.5, 1e-3)
    ramp = np.clip(lum / reference, 0, 1) ** 0.75
    return low + (high - low) * ramp[:, :, None]


def build_ring() -> None:
    rgb = remove_backdrop(load("metal-ring.jpg"))
    lum = luminance(rgb)
    # La couronne est opaque sur sa masse, translucide sur ses stries.
    # Seuils relevés : la planche d'origine contient un disque gris très sombre autour
    # de la couronne ; sans ce plancher, il apparaîtrait comme un voile carré.
    body = smoothstep(lum, 0.055, 0.150)
    alpha = feather(smoothstep(body, 0.30, 0.95) * 0.95, 1.2)
    colour = steel_colour(rgb, "#25323d", "#e2eef6")
    save(*resize(*square(*crop_to_content(colour, alpha), fill=0.97), EXPORT), "jarvis-core-ring.png")


def build_veil() -> None:
    """Anneau de verre strié : détouré d'un damier gris, sans halo résiduel."""
    rgb = load("glass-ring.jpg")
    lum, sat = luminance(rgb), chroma(rgb)
    glass = (sat > 0.045) | ((lum < 0.55) & (lum > 0.03))
    solid = np.asarray(
        Image.fromarray((glass * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(5)),
        dtype=np.float32,
    ) / 255.0
    ys, xs = np.where(solid > 0.5)
    centre_x, centre_y = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    radius = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2
    yy, xx = np.mgrid[0:rgb.shape[0], 0:rgb.shape[1]]
    radial = np.clip((1.04 - np.sqrt((xx - centre_x) ** 2 + (yy - centre_y) ** 2) / radius) / 0.05, 0, 1)
    alpha = solid * radial
    # Les carreaux clairs du damier ne doivent pas rester collés au verre.
    alpha = np.where((sat < 0.035) & (lum > 0.70), 0, alpha)
    alpha = feather(alpha, 1.0) * np.clip(lum * 2.2 + 0.35, 0, 1)
    colour = steel_colour(rgb, "#21313c", "#cfe7f2") * 0.92
    save(*resize(*square(*crop_to_content(colour, alpha), fill=0.94), EXPORT), "jarvis-core-veil.png")


def build_disc() -> None:
    rgb = remove_backdrop(load("cyan-disc.jpg"), strength=1.0)
    lum = luminance(rgb)
    alpha = feather(smoothstep(lum, 0.015, 0.20), 1.0)
    save(*resize(*square(*crop_to_content(np.clip(rgb * 1.10, 0, 1), alpha), fill=0.90), EXPORT), "jarvis-core-disc.png")


def build_light() -> None:
    """Orbe centrale : uniquement le cœur très lumineux, pas le disque cyan complet."""
    rgb = remove_backdrop(load("core-glow.jpg"))
    lum = luminance(rgb)
    bright = lum > 0.62
    ys, xs = np.where(bright)
    if not len(xs):
        raise SystemExit("Cœur lumineux introuvable dans core-glow.jpg")
    centre_x, centre_y = int(np.median(xs)), int(np.median(ys))
    radius = int(max(xs.max() - xs.min(), ys.max() - ys.min()) * 0.95)
    side = radius * 2
    top, left = max(centre_y - radius, 0), max(centre_x - radius, 0)
    crop = rgb[top:top + side, left:left + side]
    height, width = crop.shape[:2]
    yy, xx = np.mgrid[0:height, 0:width]
    distance = np.sqrt((xx - width / 2) ** 2 + (yy - height / 2) ** 2) / (min(width, height) / 2)
    circular = 1.0 - smoothstep(distance, 0.55, 1.0)
    local = luminance(crop)
    alpha = feather(smoothstep(local, 0.18, 0.85) * circular, 2.0)
    colour = steel_colour(crop, "#3fb6e6", "#ffffff")
    save(*resize(colour, alpha, EXPORT), "jarvis-core-light.png")


LAYERS = (
    # (fichier, diamètre CSS, mode de fusion, opacité repos, opacité parole)
    ("jarvis-core-ring.png", 380, "normal", .62, .86),
    ("jarvis-core-veil.png", 330, "normal", .72, .95),
    ("jarvis-core-disc.png", 286, "screen", .58, .92),
    ("jarvis-core-light.png", 210, "screen", .70, 1.0),
)


def preview() -> None:
    """Simule un rendu repos / parole pour contrôler les couches hors navigateur."""
    backdrop = Image.open(ASSETS / "command-room.jpg").convert("RGB").resize((1376, 768), Image.Resampling.LANCZOS)
    base = np.asarray(backdrop, dtype=np.float32) / 255.0
    centre = (688, 332)

    def place(name: str, diameter: int) -> tuple[np.ndarray, np.ndarray]:
        image = Image.open(ASSETS / name).convert("RGBA").resize((diameter, diameter), Image.Resampling.LANCZOS)
        data = np.asarray(image, dtype=np.float32) / 255.0
        return data[:, :, :3], data[:, :, 3]

    def compose(index: int) -> Image.Image:
        canvas = base.copy()
        for name, diameter, blend, rest, speaking in LAYERS:
            rgb, alpha = place(name, diameter)
            opacity = (speaking if index else rest) * alpha
            top, left = centre[1] - diameter // 2, centre[0] - diameter // 2
            area = canvas[top:top + diameter, left:left + diameter]
            if blend == "screen":
                area[:] = 1 - (1 - area) * (1 - rgb * opacity[:, :, None])
            else:
                area[:] = area * (1 - opacity[:, :, None]) + rgb * opacity[:, :, None]
        return Image.fromarray((canvas.clip(0, 1) * 255).astype(np.uint8), "RGB")

    for index, name in enumerate((".preview-core-rest.jpg", ".preview-core-speaking.jpg")):
        compose(index).save(ROOT / name, quality=92)
    print("Aperçus : .preview-core-rest.jpg et .preview-core-speaking.jpg")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="génère aussi les rendus de contrôle")
    arguments = parser.parse_args()
    build_ring()
    build_veil()
    build_disc()
    build_light()
    if arguments.preview:
        preview()
