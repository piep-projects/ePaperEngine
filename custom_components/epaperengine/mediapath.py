"""From a file on disk to something the browser may load (FSD §3.4, §15).

The images live under Home Assistant's ``media`` directory, and Home Assistant
serves them itself — no second port, no mixed content behind HTTPS, and it works
from outside the house. The price is that ``media`` is authenticated: an ``<img>``
tag carries no bearer token, so the frontend needs a **signed** path.

**Measured on ha-test1, HA 2026.8.2 (2026-08-21)** — this is the resolution of
the open point in FSD §15:

===========================================================  =====================
call                                                         result
===========================================================  =====================
``auth/sign_path`` on ``/media/local/<mount>/…/current.jpg``  200, ``image/jpeg``,
                                                             132.296 B, ``expires``
                                                             is honoured
``media_source/resolve_media`` on the same file              identical URL, but a
                                                             fixed 24 h lifetime
the same URL without ``?authSig=``                           401
===========================================================  =====================

So ``auth/sign_path`` it is, and the **frontend** signs: the integration hands
out the unsigned path (only it knows ``media.root``), the panel and the card sign
it right before they set ``src``. That keeps a signature — a thing with an expiry
date — out of the store, and lets a page that stays open re-sign on its own.

What is left here is the mapping from a filesystem path to that URL path, and it
is not a string constant: ``media_dirs`` is configurable, and on ha-test1 the NAS
is mounted *below* ``/media`` as ``/media/media_test_ocean3``.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from homeassistant.core import HomeAssistant

# Fallback root of the image store when ``media.root`` is unset (FSD §3.4).
DEFAULT_MEDIA_ROOT = "/media/epaperengine"

# The tree below the root, as fixed in FSD §3.4. English folder names
# [Festlegung 2026-08-21] — renaming them after the first add-on run would be a
# migration.
SUBDIR_PHOTOS = "photos"
SUBDIR_BACKGROUNDS = "backgrounds"
SUBDIR_WALL = "wall"
SUBDIR_PREVIEW = "preview"
SUBDIR_PREVIEW_PHOTOS = "preview/photos"

WALL_CURRENT = "wall/current.png"
PREVIEW_CURRENT = "preview/current.jpg"


def media_root(config: dict) -> str:
    """The configured root of the image store, or the specification's default."""
    root = ((config or {}).get("media") or {}).get("root")
    return str(root).rstrip("/") if root else DEFAULT_MEDIA_ROOT


def media_url_path(hass: HomeAssistant, file_path: str) -> str | None:
    """``/media/<dir_id>/<rest>`` for a file below one of HA's media dirs.

    ``None`` when the file lies outside all of them — then no amount of signing
    would help, and the caller has to say so rather than render a broken image.
    """
    target = PurePosixPath(file_path)
    for dir_id, base in (hass.config.media_dirs or {}).items():
        try:
            relative = target.relative_to(PurePosixPath(base))
        except ValueError:
            continue
        return f"/media/{dir_id}/{relative}"
    return None


def wall_url_path(hass: HomeAssistant, config: dict) -> str | None:
    """Unsigned path of the full-size image currently on the wall."""
    return media_url_path(hass, f"{media_root(config)}/{WALL_CURRENT}")


def preview_url_path(hass: HomeAssistant, config: dict) -> str | None:
    """Unsigned path of the small preview (856×482 JPEG, FSD §3.4)."""
    return media_url_path(hass, f"{media_root(config)}/{PREVIEW_CURRENT}")
