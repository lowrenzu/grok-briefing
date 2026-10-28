#!/usr/bin/env python3
"""Compose le cœur holographique de JARVIS : quatre anneaux concentriques animés.

Ordre d'assemblage (du fond vers l'avant) :

1. `jarvis-core-ring.png`   — couronne d'acier sombre (vue frontale)
2. `jarvis-core-veil.png`   — mécanique interne (anneaux et pignons)
3. `jarvis-core-disc.png`   — anneau HUD cyan
4. `jarvis-core-light.png`  — œil lumineux central

Chaque calque est un PNG RGBA carré, centré, exporté à `EXPORT` pixels de côté.
Les sources (`tools/sources/`) sont les quatre plaques détachées sur fond blanc :
chaque pièce est isolée par son écart au blanc, puis recadrée au plus juste pour que
les quatre calques partagent exactement le même centre.

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
EXPORT = 896      # 1,8× le diamètre CSS maximal (500 px) : net sur écran Retina
FALLBACK = 640    # repli PNG pour les navigateurs sans AVIF
AVIF_QUALITY = 58 # même rendu que le PNG à l'œil, dix fois plus léger


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
    """Écrit la version servie (.avif, légère) et le repli .png."""
    data = np.dstack([rgb, alpha]).clip(0, 1) * 255.0
    image = Image.fromarray(data.astype(np.uint8), "RGBA")
    if image.size != (EXPORT, EXPORT):
        image = image.resize((EXPORT, EXPORT), Image.Resampling.LANCZOS)
    stem = Path(name).stem
    web = ASSETS / f"{stem}.avif"
    image.save(web, "AVIF", quality=AVIF_QUALITY, speed=6)
    fallback = ASSETS / f"{stem}.png"
    small = image.resize((FALLBACK, FALLBACK), Image.Resampling.LANCZOS)
    small.save(fallback, optimize=True)
    print(f"{name:18s} avif {web.stat().st_size:>7,} o · png {fallback.stat().st_size:>7,} o"
          f"  bbox {image.getchannel('A').getbbox()}")


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


def ink_field(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Écart au fond blanc des planches : noirceur et couleur, sans le grain JPEG."""
    lum = rgb.max(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    return np.maximum(1.0 - lum, sat * 0.9), lum, sat


def radial_mask(rgb: np.ndarray, alpha: np.ndarray, radius: float) -> np.ndarray:
    """Masque circulaire normalisé (1 au centre, 0 au bord) sur le rayon mesuré."""
    cx, cy, _ = measure(alpha, 0.5)
    yy, xx = np.mgrid[0:rgb.shape[0], 0:rgb.shape[1]]
    return np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / radius


def finish(rgb: np.ndarray, alpha: np.ndarray, name: str) -> None:
    """Recadre au plus juste, remet le carré et exporte."""
    cx, cy, radius = measure(alpha, 0.5)
    cut_rgb, cut_alpha, _ = crop_circle(rgb, alpha, cx, cy, radius * 1.02)
    save(*to_square(cut_rgb, cut_alpha, EXPORT), name)


def build_crown() -> None:
    """Couronne d'acier : anneau extérieur, LED blanches, logement central opaque."""
    rgb = load("crown.jpg")
    ink, lum, sat = ink_field(rgb)
    alpha = smooth(ink, 0.07, 0.20)
    _, _, radius = measure(alpha, 0.5)
    distance = radial_mask(rgb, alpha, radius)
    # Le logement central est comblé : aucune transparence à l'intérieur du rond.
    hole = 1.0 - smooth(distance, 0.60, 0.64)
    alpha = np.maximum(alpha, hole)
    low = np.array([0x07 / 255, 0x0d / 255, 0x13 / 255], dtype=np.float32)
    blank = (lum > 0.92) & (sat < 0.04)
    rgb = np.where((blank & (hole > 0.5))[:, :, None], low, rgb)
    # Métal du logement : volontairement plus sombre que la planche, pour que le cœur
    # reste un objet noir dans le cockpit et non un dôme gris.
    rgb = np.clip((np.clip(rgb, 0, 1) ** 1.35) * np.array([0.90, 0.96, 1.0], dtype=np.float32), 0, 1)
    finish(rgb, feather(alpha, 1.0), "jarvis-core-ring.png")


def build_veil() -> None:
    """Mécanique interne : anneaux et pignons concentriques, acier sombre."""
    rgb = load("gears.jpg")
    ink, _, _ = ink_field(rgb)
    # Seuil haut : le voile de compression autour des pignons ne doit pas laisser
    # de brume carrée sur le fond.
    alpha = smooth(ink, 0.16, 0.34)
    rgb = np.clip((np.clip(rgb, 0, 1) ** 1.28) * 0.95, 0, 1)
    finish(rgb, feather(alpha, 0.8), "jarvis-core-veil.png")


def build_disc() -> None:
    """Anneau HUD cyan : la lumière sort du logement, le centre reste ouvert."""
    rgb = load("hud-ring.jpg")
    ink, _, _ = ink_field(rgb)
    alpha = smooth(ink, 0.03, 0.10)
    finish(np.clip(rgb * 1.04, 0, 1), feather(alpha, 0.9), "jarvis-core-disc.png")


def build_disc_tint(source: str, name: str, gain: float) -> None:
    """Variantes colorées de l'anneau HUD, utilisées comme nappes de voix."""
    rgb = load(source)
    ink, _, _ = ink_field(rgb)
    alpha = smooth(ink, 0.03, 0.10)
    finish(np.clip(rgb * gain, 0, 1), feather(alpha, 0.9), name)


def build_light() -> None:
    """Œil lumineux : le noyau blanc est comblé, le halo reste fondu."""
    rgb = load("core-eye.jpg")
    ink, lum, _ = ink_field(rgb)
    alpha = smooth(ink, 0.02, 0.16)
    # Le halo blanc de la planche est coupé net au bord du cerclage : sinon il forme
    # un anneau laiteux autour de l'œil une fois posé sur le logement sombre.
    bezel = smooth(1.0 - lum, 0.20, 0.42)
    _, _, radius = measure(alpha, 0.5)
    bezel_cx, bezel_cy, bezel_r = measure(bezel, 0.5)
    yy, xx = np.mgrid[0:rgb.shape[0], 0:rgb.shape[1]]
    bevel = np.sqrt((xx - bezel_cx) ** 2 + (yy - bezel_cy) ** 2) / bezel_r
    alpha = np.minimum(alpha, 1.0 - smooth(bevel, 0.94, 1.02))
    distance = np.sqrt((xx - bezel_cx) ** 2 + (yy - bezel_cy) ** 2) / bezel_r
    # Noyau central : opaque, sinon le blanc laisserait un trou au milieu de l'œil.
    alpha = np.maximum(alpha, 1.0 - smooth(distance, 0.55, 0.68))
    finish(np.clip(rgb, 0, 1), feather(alpha, 1.2), "jarvis-core-light.png")


LAYERS = (
    # (fichier, part du diamètre extérieur, mode de fusion, opacité repos, opacité parole)
    ("jarvis-core-ring.png", 1.00, "normal", .95, 1.0),
    ("jarvis-core-veil.png", .90, "normal", .9, 1.0),
    ("jarvis-core-disc.png", .72, "screen", .92, 1.0),
    ("jarvis-core-light.png", .40, "screen", .95, 1.0),
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
    build_disc_tint("hud-violet.jpg", "jarvis-core-hud-violet.png", 1.04)
    build_disc_tint("hud-ambre.jpg", "jarvis-core-hud-ambre.png", 1.02)
    build_light()
    if arguments.preview:
        preview()
