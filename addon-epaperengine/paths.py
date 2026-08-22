"""Where the image store lives (FSD §3.4).

The specification writes ``/media/epaperengine/`` as a constant. It cannot be
one, and the reason is measured rather than argued: Home Assistant mounts
network storage as a **subdirectory** of ``/media`` — on the test instance the
NAS share sits at ``/media/media_test_ocean3/`` [measured 2026-08-21, ``ha
mounts info``: CIFS ``192.168.178.7:homes/ha_test_media``, usage ``media``].
``/media`` itself is the local disk of the Home Assistant machine. Writing the
literal path from §3.4 would therefore put a few hundred photos plus their
2560×1440 renderings on the VM's own 8 GB of free space instead of on the NAS
the specification asks for — and the mount name differs between test and
production, so no constant can be right for both.

Hence: the root is configuration (``media.root`` in the integration store), and
the path from the specification is only the fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# What FSD §3.4 writes. Used when nothing is configured — correct only if the
# media directory happens to be local.
DEFAULT_MEDIA_ROOT = Path("/media/epaperengine")


@dataclass(frozen=True)
class MediaPaths:
    """The tree from FSD §3.4, rooted wherever the configuration points."""

    root: Path

    @property
    def photos(self) -> Path:
        """Originals. Curated by putting files in (FSD §8.3)."""
        return self.root / "photos"

    @property
    def backgrounds(self) -> Path:
        """Guest backgrounds, originals (phase 5)."""
        return self.root / "backgrounds"

    @property
    def processed_backgrounds(self) -> Path:
        """Cropped 16:9 guest backgrounds, ready for the template.

        The same shape as ``processed_photos`` because it is the same machinery:
        ``PhotoCache`` is pointed at another source folder and writes another
        pair of directories. A second implementation of "crop, hash, thumbnail,
        prune" would be the same code with different bugs.
        """
        return self.root / "processed" / "backgrounds"

    @property
    def preview_backgrounds(self) -> Path:
        """Thumbnails for the background picker in the panel (phase 5)."""
        return self.root / "preview" / "backgrounds"

    @property
    def processed_photos(self) -> Path:
        """Cropped 16:9 sources, ready for the template."""
        return self.root / "processed" / "photos"

    @property
    def preview_photos(self) -> Path:
        """Thumbnails for the photo picker in the panel (phase 4)."""
        return self.root / "preview" / "photos"

    @property
    def wall(self) -> Path:
        """What currently hangs on the wall, plus the history."""
        return self.root / "wall"

    @property
    def preview(self) -> Path:
        """Preview of the current image, for card and panel."""
        return self.root / "preview"

    def ensure(self) -> None:
        """Create the tree. Never touches ``photos`` content, only the folders."""
        for directory in (
            self.photos,
            self.backgrounds,
            self.processed_photos,
            self.preview_photos,
            self.processed_backgrounds,
            self.preview_backgrounds,
            self.wall,
            self.preview,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def media_paths(root: str | None) -> MediaPaths:
    """Resolve the configured root, falling back to the specification's path."""
    return MediaPaths(Path(root) if root else DEFAULT_MEDIA_ROOT)


def source_folder(paths: MediaPaths, configured: str | None) -> Path:
    """The folder the photos are read from.

    ``photos.source_folder`` (FSD §4) wins when set — it lets a second album live
    outside the tree — otherwise it is ``<root>/photos``.
    """
    return Path(configured) if configured else paths.photos
