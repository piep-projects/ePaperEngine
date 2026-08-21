"""Jinja → HTML → Chromium → PNG (FSD §6.2 steps 3 and 4).

No Node, no Puppeteer. Measured 2026-08-21 in the add-on image (Chromium
151.0.7922.108, Alpine 3.24.1): ``chromium-headless-shell`` driven straight from
the command line produces an **exactly 2560×1440** screenshot in **1.11 s**,
with DejaVu text and local images rendered correctly. Puppeteer would have added
the full ``chromium`` package on top of the headless shell (282 MB of binary) and
a ``node_modules`` tree, to reach the same pixels. FSD §6.2 names
``deviceScaleFactor: 1``, which is Puppeteer vocabulary for what the CLI calls
``--force-device-scale-factor=1``.

Node stays in the image, but only for the MDC push (``delivery.py``).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from PIL import Image

from imaging import CANVAS

_LOGGER = logging.getLogger("epaperengine.render")

CHROMIUM = "/usr/bin/chromium-headless-shell"
TEMPLATES = Path(__file__).parent / "templates"

# How long the page may take before the shot is taken. Virtual time, not wall
# clock — the measured run finished in about a second.
VIRTUAL_TIME_BUDGET_MS = 5000

# Hard ceiling in wall-clock seconds, so a hung Chromium cannot wedge the queue.
TIMEOUT_S = 60

CHROMIUM_FLAGS = [
    "--headless",
    # Root inside the container, and the add-on has no use for the sandbox.
    "--no-sandbox",
    "--disable-gpu",
    # Containers get a small /dev/shm; without this Chromium dies on big pages.
    "--disable-dev-shm-usage",
    "--hide-scrollbars",
    # FSD §6.2 step 4: one CSS pixel is one panel pixel.
    "--force-device-scale-factor=1",
    f"--window-size={CANVAS[0]},{CANVAS[1]}",
    # The template pulls the photo from the media tree with a file:// URL, which
    # counts as a cross-directory local subresource.
    "--allow-file-access-from-files",
    f"--virtual-time-budget={VIRTUAL_TIME_BUDGET_MS}",
]


class RenderError(RuntimeError):
    """The run produced no usable image. Reported verbatim to the status sensor."""


_environment = Environment(
    loader=FileSystemLoader(TEMPLATES),
    # ``j2`` has to be in the list and the default has to be True. Measured
    # 2026-08-21 (Jinja 3.1.6): ``select_autoescape`` matches with ``endswith``,
    # not by file extension — ``photos.html.j2`` ends in ``.j2``, so the previous
    # ``select_autoescape(["html"])`` left autoescaping **off for every template
    # in this add-on**. Harmless while the only variable was a ``file://`` URL;
    # not harmless from the error page on, which puts exception text — the one
    # string nobody controls — into the markup.
    autoescape=select_autoescape(
        enabled_extensions=("html", "htm", "xml", "j2"),
        default_for_string=True,
        default=True,
    ),
    # A missing variable must break the run loudly. A silently empty wall image
    # is the one failure mode nobody notices until they walk past the display.
    undefined=StrictUndefined,
)


def render_html(view: str, context: dict[str, object], workdir: Path) -> Path:
    """Fill the template for ``view`` and write it next to its assets."""
    template = _environment.get_template(f"{view}.html.j2")
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / f"{view}.html"
    path.write_text(template.render(**context), encoding="utf-8")
    return path


def screenshot(html: Path, out: Path, workdir: Path) -> Image.Image:
    """Shoot the page and hand back the image, verified at panel resolution."""
    if not Path(CHROMIUM).exists():  # pragma: no cover - image build guarantees it
        raise RenderError(f"{CHROMIUM} missing from the image")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    profile = workdir / "chromium-profile"
    shutil.rmtree(profile, ignore_errors=True)

    command = [
        CHROMIUM,
        *CHROMIUM_FLAGS,
        f"--user-data-dir={profile}",
        f"--screenshot={out}",
        html.as_uri(),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=TIMEOUT_S, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"Chromium did not finish within {TIMEOUT_S}s") from exc

    if completed.returncode != 0 or not out.exists():
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise RenderError(
            f"Chromium exited {completed.returncode}: "
            + (" | ".join(detail[-3:]) if detail else "no output")
        )

    image = Image.open(out)
    image.load()
    if image.size != CANVAS:
        raise RenderError(f"screenshot is {image.size}, expected {CANVAS}")
    _LOGGER.debug("Screenshot %s at %s", out.name, image.size)
    return image.convert("RGB")
