#!/usr/bin/env python3
"""Compose le cœur holographique de JARVIS : quatre anneaux concentriques animés.

Ordre d'assemblage (du fond vers l'avant) :

1. `jarvis-core-ring.png`   — couronne d'acier sombre (vue frontale)
2. `jarvis-core-veil.png`   — anneau de verre strié
3. `jarvis-core-disc.png`   — disque HUD cyan (perspective redressée)
4. `jarvis-core-light.png`  — orbe lumineuse centrale

Chaque calque est un PNG RGBA carré, centré, exporté à `EXPORT` pixels de côté.
Les sources (`tools/sources/`) sont des images générées sur fond noir ou damier :
le fond est estimé puis retiré, les traits de repère sont effacés, et les pièces
vues en perspective sont redressées pour retrouver des cercles.

    python3 tools/build-jarvis-core.py             # écrit les quatre calques
    python3 tools/build-jarvis-core.py --preview   # + rendus de contrôle repos/parole

Prérequis (uniquement pour cette commande) : Pillow et numpy.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "viewer" / "assets"
SOURCES = ROOT / "tools" / "sources"
EXPORT = 640  # 1,7× le diamètre CSS de 380 px : net sur écran Retina


def load(name: str) -> np.ndarray:
    return np.asarray(Image.open(SOURCES / name).convert("RGB"), dtype=np.float32) / 255.0


def smooth(field: np.ndarray, low: float, high: float) -> np.ndarray:
    x = np.clip((field - low) / max(high - low, 1e-6), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def feather(alpha: np.ndarray, radius: float = 1.0) -> np.ndarray:
    image = Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8), "L")
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32) / 255.0


def despeckle(field: np.ndarray, size: int = 9) -> np.ndarray:
    """Médiane 1D horizontale puis verticale : efface les traits de repère fins."""
    height, width = field.shape
    half = size // 2
    padded = np.pad(field, ((0, 0), (half, half)), mode="edge")
    rows = np.stack([padded[:, index:index + width] for index in range(size)])
    field = np.median(rows, axis=0)
    padded = np.pad(field, ((half, half), (0, 0)), mode="edge")
    columns = np.stack([padded[index:index + height] for index in range(size)])
    return np.median(columns, axis=0)


def crop_circle(rgb: np.ndarray, alpha: np.ndarray, cx: float, cy: float, r: float,
                companion: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Découpe un disque en adoucissant le bord : aucun angle carré ne subsiste.

    `companion` est une seconde carte (luminance par exemple) découpée de la même façon.
    """
    yy, xx = np.mgrid[0:rgb.shape[0], 0:rgb.shape[1]]
    circle = 1.0 - smooth(np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r, 0.94, 1.0)
    masked = alpha * circle
    top, bottom = max(int(cy - r), 0), min(int(cy + r), rgb.shape[0])
    left, right = max(int(cx - r), 0), min(int(cx + r), rgb.shape[1])
    extra = companion[top:bottom, left:right] if companion is not None else None
    return rgb[top:bottom, left:right], masked[top:bottom, left:right], extra


def to_square(rgb: np.ndarray, alpha: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray]:
    """Redimensionne en carré (redressement de perspective + mise à l'échelle)."""
    premultiplied = np.dstack([rgb * alpha[:, :, None], alpha])
    image = Image.fromarray((premultiplied * 255).clip(0, 255).astype(np.uint8), "RGBA")
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    data = np.asarray(image, dtype=np.float32) / 255.0
    out_alpha = data[:, :, 3]
    out_rgb = np.divide(data[:, :, :3], np.maximum(out_alpha, 1e-4)[:, :, None])
    return np.clip(out_rgb, 0, 1), np.clip(out_alpha, 0, 1)


def save(rgb: np.ndarray, alpha: np.ndarray, name: str) -> None:
    data = np.dstack([rgb, alpha]).clip(0, 1) * 255.0
    image = Image.fromarray(data.astype(np.uint8), "RGBA")
    if image.size != (EXPORT, EXPORT):
        image = image.resize((EXPORT, EXPORT), Image.Resampling.LANCZOS)
    destination = ASSETS / name
    image.save(destination, optimize=True)
    print(f"{name:26s} {destination.stat().st_size:>8,} octets  bbox {image.getchannel('A').getbbox()}")


def solidify(alpha: np.ndarray, rgb: np.ndarray, fill_colour: str,
             floor: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Transforme un détourage en pastille pleine : seul l'extérieur reste transparent.

    Le fond est éliminé par un masque circulaire propre (le bruit du détourage ne laisse
    donc aucune tache), et tout l'intérieur — y compris le trou central de l'anneau —
    reçoit la matière de la pièce. `fill_colour` sert à combler ce trou.
    """
    height, width = alpha.shape
    yy, xx = np.mgrid[0:height, 0:width]
    cx, cy = (width - 1) / 2, (height - 1) / 2
    distance = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    outer = min(width, height) / 2 * 0.995
    circle = 1.0 - smooth(distance / outer, 0.985, 1.0)
    # Le contour extérieur garde un léger flou pour ne pas créneler sur le décor.
    shaped = np.maximum(feather(alpha, 0.8), circle * floor)
    shaped = np.minimum(shaped, circle)
    low = np.array([int(fill_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)], dtype=np.float32)
    filled_rgb = np.where((alpha < 0.35)[:, :, None], low, rgb)
    return np.clip(filled_rgb, 0, 1), np.clip(shaped, 0, 1)


def steel(rgb: np.ndarray, dark: str, light: str) -> np.ndarray:
    """Acier bleuté : l'éclat d'origine module un dégradé sombre → clair contrôlé."""
    low = np.array([int(dark[i:i + 2], 16) / 255 for i in (1, 3, 5)], dtype=np.float32)
    high = np.array([int(light[i:i + 2], 16) / 255 for i in (1, 3, 5)], dtype=np.float32)
    lum = rgb.max(axis=2)
    reference = max(float(np.percentile(lum[lum > 0.02], 99.5)) if (lum > 0.02).any() else 0.5, 1e-3)
    ramp = np.clip(lum / reference, 0, 1) ** 0.78
    return low + (high - low) * ramp[:, :, None]


def measure(alpha: np.ndarray, threshold: float = 0.5) -> tuple[float, float, float]:
    ys, xs = np.where(alpha > threshold)
    if not len(xs):
        raise SystemExit("Calque vide : vérifiez tools/sources/.")
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    radius = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2
    return cx, cy, radius


def build_crown() -> None:
    """Couronne d'acier : vue frontale déjà circulaire."""
    rgb = load("metal-ring.jpg")
    lum = rgb.max(axis=2)
    body = smooth(lum, 0.010, 0.050)
    cx, cy, radius = measure(lum > 0.05)
    cut_rgb, cut_alpha, cut_lum = crop_circle(rgb, body, cx, cy, radius * 1.01, companion=lum)
    # Métal sombre : la masse reste presque noire, seules les arêtes chromées s'allument.
    colour = np.clip(steel(cut_rgb, "#0d141c", "#f2fbff") ** 1.45 * 0.92, 0, 1)
    colour, cut_alpha = solidify(cut_alpha, colour, "#070d13")
    save(*to_square(colour, cut_alpha, EXPORT), "jarvis-core-ring.png")


def build_veil() -> None:
    """Anneau de verre strié, détouré d'un damier gris (pas de halo résiduel)."""
    rgb = load("glass-ring.jpg")
    lum, sat = rgb.max(axis=2), rgb.max(axis=2) - rgb.min(axis=2)
    glass = ((sat > 0.045) | ((lum < 0.55) & (lum > 0.03))).astype(np.float32)
    solid = np.asarray(
        Image.fromarray((glass * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(5)),
        dtype=np.float32,
    ) / 255.0
    # La planche contient des repères (traits fins) : on les efface avant de découper.
    # La planche laisse une large marge noire : on cadre la bande utile en proportion.
    top, bottom = int(rgb.shape[0] * 0.218), int(rgb.shape[0] * 0.770)
    solid = despeckle(solid[top:bottom], 9)
    cx, cy, radius = measure(solid)
    solid = np.where((sat[top:bottom] < 0.035) & (lum[top:bottom] > 0.70), 0, solid)
    cut_rgb, cut_alpha, cut_lum = crop_circle(
        rgb[top:bottom], solid, cx, cy, radius * 1.02, companion=lum[top:bottom]
    )
    cut_alpha = cut_alpha * np.clip(cut_lum * 3.4 - 0.12, 0, 1)
    colour = np.clip(steel(cut_rgb, "#0f1d27", "#dceff9") ** 1.35 * 1.05, 0, 1)
    colour, cut_alpha = solidify(feather(cut_alpha, 1.0), colour, "#0a141d")
    save(*to_square(colour, cut_alpha, EXPORT), "jarvis-core-veil.png")


def build_disc() -> None:
    """Disque HUD cyan, vu de face : aucune perspective à corriger, aucun métal voisin."""
    rgb = load("cyan-disc.jpg")
    lum = rgb.max(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    mask = despeckle(smooth(lum, 0.04, 0.18) * np.maximum(smooth(sat, 0.02, 0.10), 0.55), 7)
    cx, cy, radius = measure(mask, threshold=0.30)
    cut_rgb, cut_alpha, _ = crop_circle(rgb, mask, cx, cy, radius * 1.0)
    colour, cut_alpha = solidify(feather(cut_alpha, 1.0), np.clip(cut_rgb * 1.05, 0, 1), "#04121c")
    save(*to_square(colour, cut_alpha, EXPORT), "jarvis-core-disc.png")


def build_light() -> None:
    """Orbe lumineuse : disque plein, net, dont les rayons suivent la source.

    La source empile un arc d'acier et l'orbe. On repère le centre de l'orbe (cyan
    saturé), puis on reconstruit un disque parfaitement circulaire : la texture de la
    source module la couleur, la teinte de comblement occupe les zones sombres.
    """
    rgb = load("orb-glow.jpg")
    lum = rgb.max(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    ys, xs = np.where((sat > 0.25) & (lum > 0.35))
    if not len(xs):
        raise SystemExit("Orbe centrale introuvable dans orb-glow.jpg")
    cx, cy = float(xs.mean()), float(ys.mean())
    radius = 104.0
    height, width = lum.shape
    yy, xx = np.mgrid[0:height, 0:width]
    distance = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / radius
    disc = 1.0 - smooth(distance, 0.90, 1.0)
    texture = np.clip(lum * 1.35, 0, 1) ** 0.9
    low = np.array([0x08 / 255, 0x2a / 255, 0x3d / 255], dtype=np.float32)
    high = np.array([0.72, 0.95, 1.0], dtype=np.float32)
    colour = low + (high - low) * feather(texture, 2.0)[:, :, None]
    # Éclaircissement central : le noyau de l'orbe reste blanc.
    core = 1.0 - smooth(distance, 0.10, 0.45)
    colour = np.clip(colour + core[:, :, None] * np.array([0.55, 0.42, 0.30], dtype=np.float32), 0, 1)
    cut_rgb, cut_alpha, _ = crop_circle(colour, disc, cx, cy, radius)
    save(*to_square(cut_rgb, feather(cut_alpha, 1.4), EXPORT), "jarvis-core-light.png")


LAYERS = (
    # (fichier, part du diamètre extérieur, mode de fusion, opacité repos, opacité parole)
    ("jarvis-core-ring.png", 1.00, "normal", .90, 1.0),
    ("jarvis-core-disc.png", .78, "screen", .85, 1.0),
    ("jarvis-core-veil.png", .66, "screen", .45, .80),
    ("jarvis-core-light.png", .30, "screen", .88, 1.0),
)


def preview() -> None:
    """Simule un rendu repos / parole dans le décor, hors navigateur."""
    backdrop = Image.open(ASSETS / "command-room.jpg").convert("RGB").resize((1376, 768), Image.Resampling.LANCZOS)
    base = np.asarray(backdrop, dtype=np.float32) / 255.0
    centre = (688, 332)
    outer = 300

    def compose(index: int) -> Image.Image:
        canvas = base.copy()
        for name, fraction, blend, rest, speaking in LAYERS:
            diameter = int(outer * fraction)
            image = Image.open(ASSETS / name).convert("RGBA").resize((diameter, diameter), Image.Resampling.LANCZOS)
            data = np.asarray(image, dtype=np.float32) / 255.0
            rgb, alpha = data[:, :, :3], data[:, :, 3]
            opacity = alpha * (speaking if index else rest)
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
    build_crown()
    build_veil()
    build_disc()
    build_light()
    if arguments.preview:
        preview()
