"""The image chain: crop, dither, preview (FSD §6.2 steps 4–7, §7).

The dithering is ``phase1/dither_spectra.py`` — the same palette, the same
gamma, both measured at the real panel on 2026-08-19. Do not tune the numbers
here without a fresh measurement at the wall; the reason they look arbitrary is
that they *are* the panel's, not a designer's.

**Gamma runs exactly once, at the very end.** That is a deviation from FSD §8.3,
which puts the dithering into the photo cache, and it is measured: dithering an
already-dithered image a second time with gamma 0.85 changes **1.8 % of the
pixels** [measured 2026-08-21 in the add-on image, Pillow 12.2.0], because the
gamma is applied twice and pushes every colour off the palette again. Since the
whole operation costs **0.10 s** on 2560×1440, there is nothing to gain from
caching it and a visible amount to lose. The cache therefore holds the *crop*
(§8.3's expensive half: NAS read, JPEG decode, Lanczos resize), and gamma plus
dither happen once per run on the finished screenshot.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

# Panel resolution, exactly 1:1 [belegt, FSD §3.3] — layouts may bleed to the edge.
CANVAS = (2560, 1440)

# The six Spectra primaries. Estimated, not measured at the panel — the point of
# dithering against them ourselves is that *we* decide which primaries a mixed
# tone is built from: pink from red+white, not red+yellow (which reads orange).
SPECTRA = [
    (0, 0, 0),
    (255, 255, 255),
    (220, 30, 30),
    (240, 200, 30),
    (30, 60, 180),
    (30, 140, 70),
]

# < 1 brightens. 0.85 was found right at the panel on 2026-08-19 [belegt].
GAMMA = 0.85

# Preview formats from FSD §3.4, both measured: the dither raster does not
# survive downscaling, so a preview shows the motif and never the Spectra
# effect — which is why JPEG is allowed here and PNG would only waste space.
PREVIEW_CURRENT = (856, 482)  # card and panel, ~99 KB at q85
PREVIEW_THUMB = (320, 180)  # photo picker, ~15 KB at q85
PREVIEW_QUALITY = 85

# Crop quality for the photo cache. Straight from phase1/prepare_photo.py.
# JPEG is safe *here* because the file is not dithered yet — the ban in FSD §7
# is about dithered material, where compression destroys the raster.
CROP_QUALITY = 95


def _palette_image() -> Image.Image:
    """A 1×1 P-mode image carrying the Spectra palette, for ``quantize``."""
    palette = Image.new("P", (1, 1))
    flat = [value for colour in SPECTRA for value in colour]
    flat += [0] * (768 - len(flat))  # fill up the rest of the 256-entry palette
    palette.putpalette(flat)
    return palette


def crop_to_canvas(image: Image.Image, top_share: float = 0.5) -> Image.Image:
    """Cut to 16:9 and scale to 2560×1440.

    ``top_share`` is the fraction of the vertical trim taken off the top.
    ``phase1/prepare_photo.py`` chose it per picture by eye (0.27 for the
    bouquet, 0.35 for the tulip field); an automated cache has nobody to ask, so
    it centres. Photographs put the subject in the middle often enough that this
    is the least bad rule, and the panel can be given a per-photo override later
    without invalidating the cache format.
    """
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size
    target_ratio = CANVAS[0] / CANVAS[1]

    need_height = round(width / target_ratio)
    if need_height <= height:  # too tall — trim top and bottom
        trim = height - need_height
        top = round(trim * top_share)
        image = image.crop((0, top, width, top + need_height))
    else:  # too wide — trim left and right, always centred
        need_width = round(height * target_ratio)
        left = (width - need_width) // 2
        image = image.crop((left, 0, left + need_width, height))

    return image.resize(CANVAS, Image.LANCZOS)


def dither_spectra(image: Image.Image, gamma: float = GAMMA) -> Image.Image:
    """Gamma-correct, then Floyd–Steinberg against the six primaries.

    Returns **RGB**, not the palette mode ``quantize`` produces. A palette PNG
    would be 24 % smaller and encode twice as fast [measured 2026-08-21: 402 KB /
    0.18 s against 526 KB / 0.32 s], but the file that provably reached the panel
    on 2026-08-19 was RGB, and the new push path is enough of a new variable for
    one phase. Worth revisiting once a picture hangs.
    """
    image = image.convert("RGB")
    if gamma != 1.0:
        lut = [min(255, round(255 * ((i / 255) ** gamma))) for i in range(256)]
        image = image.point(lut * 3)
    quantized = image.quantize(palette=_palette_image(), dither=Image.Dither.FLOYDSTEINBERG)
    return quantized.convert("RGB")


def save_png(image: Image.Image, path: Path) -> None:
    """Write the wall image.

    Without ``optimize=True`` on purpose: it saves 11 % of the bytes and costs
    **2.9 s instead of 0.3 s** [measured 2026-08-21] — a bad trade for a file
    that is fetched once over the LAN.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def save_crop(image: Image.Image, path: Path) -> None:
    """Write a cached crop (not dithered — see the module docstring)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=CROP_QUALITY)


def preview_bytes(image: Image.Image, size: tuple[int, int]) -> bytes:
    """Scale down for the frontend. Never done in the browser (FSD §3.4)."""
    small = image.convert("RGB").resize(size, Image.LANCZOS)
    buffer = io.BytesIO()
    small.save(buffer, format="JPEG", quality=PREVIEW_QUALITY)
    return buffer.getvalue()
