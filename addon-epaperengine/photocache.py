"""The photo cache (FSD §8.3, phase 3 steps 5 and 6).

Curation is "put the file in the folder". Everything else follows from that:
the cache has to notice new files, notice deleted ones, and it must never make
the render run wait for a few hundred JPEGs to be decoded off a NAS.

**Identity is the content hash, not the modification time.** A cached crop is
named after the SHA-256 of its source bytes, so two copies of the same picture
collapse into one entry and a file that changed is a different entry, whatever
its timestamp claims. That is the lesson from the GardenESP static-file deploy,
where mtime lied after unzipping.

The one concession: hashing every source on every run means reading the whole
album over the network **every 15 minutes** (FSD §6.1) — for 200 photos at 5 MB
that is a gigabyte of NAS traffic per run, for a question whose answer is almost
always "nothing changed". So the hash of a file is remembered under its
``(size, mtime_ns)`` and only recomputed when one of those moves. The gap this
leaves is a file that changes content while keeping both its size and its
timestamp to the nanosecond; ``refresh(force=True)`` closes it. The distinction
that matters is that mtime is used to decide **whether to look**, never to
decide **what a file is**.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

import imaging

_LOGGER = logging.getLogger("epaperengine.photos")

# What counts as a photo. Deliberately narrow — the folder is curated by hand,
# and a stray .DS_Store or thumbnail should not become a wall image.
SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff", ".bmp"}

# Read in blocks so a 50 MB raw file does not land in memory in one piece.
_HASH_BLOCK = 1 << 20


@dataclass(frozen=True)
class Photo:
    """One cached picture."""

    digest: str  # SHA-256 of the source bytes — the identity
    source: str  # path relative to the source folder, for humans and the panel
    crop: Path  # 2560×1440, cropped, *not* dithered


@dataclass
class CacheReport:
    """What a refresh did. Goes into the log and into ``/health``."""

    total: int = 0
    added: int = 0
    removed: int = 0
    unreadable: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.unreadable is None:
            self.unreadable = []


class PhotoCache:
    """Keeps ``processed/photos/`` in step with the source folder."""

    def __init__(self, source: Path, processed: Path, preview: Path, memo_path: Path) -> None:
        self._source = source
        self._processed = processed
        self._preview = preview
        self._memo_path = memo_path
        self._memo: dict[str, dict[str, Any]] = self._load_memo()
        self._photos: list[Photo] = []

    # --- memo -----------------------------------------------------------------
    def _load_memo(self) -> dict[str, dict[str, Any]]:
        try:
            return dict(json.loads(self._memo_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return {}

    def _save_memo(self) -> None:
        self._memo_path.parent.mkdir(parents=True, exist_ok=True)
        self._memo_path.write_text(json.dumps(self._memo), encoding="utf-8")

    def _digest(self, path: Path, force: bool) -> str:
        """Content hash, skipping the read when size and mtime are untouched."""
        stat = path.stat()
        key = str(path)
        remembered = self._memo.get(key)
        if (
            not force
            and remembered
            and remembered.get("size") == stat.st_size
            and remembered.get("mtime_ns") == stat.st_mtime_ns
        ):
            return str(remembered["digest"])

        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            while block := handle.read(_HASH_BLOCK):
                hasher.update(block)
        digest = hasher.hexdigest()
        self._memo[key] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "digest": digest,
        }
        return digest

    # --- refresh --------------------------------------------------------------
    def refresh(self, force: bool = False) -> CacheReport:
        """Bring the cache in line with the folder. Blocking — call in a thread."""
        report = CacheReport()
        self._processed.mkdir(parents=True, exist_ok=True)
        self._preview.mkdir(parents=True, exist_ok=True)

        if not self._source.is_dir():
            raise FileNotFoundError(f"photo folder does not exist: {self._source}")

        photos: list[Photo] = []
        seen: set[str] = set()
        # Sorted, so the deterministic slot of FSD §5 maps onto a stable order.
        for path in sorted(self._source.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUFFIXES:
                continue
            if path.name.startswith("."):  # AppleDouble and friends
                continue
            try:
                digest = self._digest(path, force)
            except OSError as exc:
                report.unreadable.append(f"{path.name}: {exc}")
                continue

            crop = self._processed / f"{digest}.jpg"
            if not crop.exists() or force:
                try:
                    self._build(path, digest, crop)
                except (OSError, UnidentifiedImageError, ValueError) as exc:
                    # One broken file must not cost the whole album.
                    report.unreadable.append(f"{path.name}: {exc}")
                    continue
                report.added += 1

            seen.add(digest)
            photos.append(Photo(digest=digest, source=str(path.relative_to(self._source)), crop=crop))

        report.removed = self._prune(seen)
        report.total = len(photos)
        self._photos = photos
        self._write_index(photos)
        self._save_memo()
        return report

    def _build(self, source: Path, digest: str, crop: Path) -> None:
        """Decode, crop to 2560×1440, write the crop and its thumbnail."""
        with Image.open(source) as original:
            cropped = imaging.crop_to_canvas(original)
        imaging.save_crop(cropped, crop)
        thumb = self._preview / f"{digest}.jpg"
        thumb.write_bytes(imaging.preview_bytes(cropped, imaging.PREVIEW_THUMB))
        _LOGGER.info("Cached %s -> %s", source.name, crop.name)

    def _prune(self, keep: set[str]) -> int:
        """Drop crops and thumbnails whose source is gone.

        Driven by the hash set, not by a bookkeeping file: whatever is not backed
        by a source right now does not belong here, even if the index went
        missing.
        """
        removed = 0
        for directory in (self._processed, self._preview):
            for path in directory.glob("*.jpg"):
                if path.stem in keep:
                    continue
                try:
                    path.unlink()
                    removed += 1
                except OSError as exc:
                    _LOGGER.warning("Could not remove %s: %s", path, exc)
        # Forget memo entries whose file disappeared, so the file does not grow
        # without bound as photos come and go.
        self._memo = {key: value for key, value in self._memo.items() if Path(key).exists()}
        return removed

    def _write_index(self, photos: list[Photo]) -> None:
        """Map hash back to a human name — the panel needs it in phase 4."""
        index = {photo.digest: photo.source for photo in photos}
        (self._processed / "index.json").write_text(
            json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8"
        )

    # --- selection ------------------------------------------------------------
    @property
    def photos(self) -> list[Photo]:
        return list(self._photos)

    def find(self, digest: str) -> Photo | None:
        """The entry with this content hash, or ``None`` if it is gone.

        What the guest view picks by (FSD §8.4): a background is *chosen* in the
        panel, not rotated, so it is addressed by its identity rather than by a
        counter. ``None`` is an answer, not a failure — a background whose file
        was deleted must cost the greeting its picture, never the whole run.
        """
        for photo in self._photos:
            if photo.digest == digest:
                return photo
        return None

    def pick(self, slot: int) -> Photo:
        """Map the integration's deterministic counter onto a file (FSD §5).

        The counter comes from Home Assistant (``now // interval``) so that an
        accidental extra render run shows the *same* picture and does not burn a
        panel refresh. Adding a photo shifts the sequence — that is the price of
        a stable order without a stored cursor, and it costs at most one wrong
        picture in one interval.
        """
        if not self._photos:
            raise LookupError(f"no usable photo in {self._source}")
        return self._photos[slot % len(self._photos)]
