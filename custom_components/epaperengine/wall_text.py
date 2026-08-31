"""The language the wall speaks (FSD §3.0a, Festlegung P9 2026-08-21).

The rendered views follow ``hass.language`` like every other surface of this
project: the integration puts the language token into the render document, the
add-on picks the matching catalog, English is base and fallback. That keeps the
one public repo consistent — a German household gets a German wall, everybody
else gets the base language, and neither costs a code change.

**Translations are data, not code** — same rule as ``frontend_i18n/``: another
language is another JSON file next to these two, and ``tests/test_translations.py``
holds them congruent (same keys, no empty values, same placeholders).

Deliberately more forgiving than the templates around it: Jinja runs with
``StrictUndefined`` so a missing *variable* breaks the run loudly, but a missing
*catalog key* falls back to English and then to the key itself. The reason is
narrow — the one page that must never fail to render is the error page, and it
would be absurd for a missing German string to be the thing that stops
ePaperEngine from saying it is broken.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

_LOGGER = logging.getLogger("epaperengine.wall_text")

CATALOG_DIR = Path(__file__).parent / "templates" / "i18n"
BASE_LANGUAGE = "en"

_loaded: dict[str, dict[str, str]] = {}


def _catalog(language: str) -> dict[str, str]:
    """Read one catalog file, memoised. Unknown language → empty."""
    if language not in _loaded:
        path = CATALOG_DIR / f"{language}.json"
        try:
            _loaded[language] = {
                str(k): str(v) for k, v in json.loads(path.read_text("utf-8")).items()
            }
        except (OSError, ValueError):
            _loaded[language] = {}
    return _loaded[language]


def normalise(language: str | None) -> str:
    """``de-DE`` → ``de``; anything without a catalog → the base language.

    Home Assistant hands out region-tagged tokens (``en-GB``, ``pt-BR``). The
    catalogs are per language, so the region is dropped rather than turned into
    a second set of files nobody maintains.
    """
    token = str(language or "").split("-")[0].strip().lower()
    if token and _catalog(token):
        return token
    if token and token != BASE_LANGUAGE:
        _LOGGER.info("No wall catalog for %r — falling back to %s", language, BASE_LANGUAGE)
    return BASE_LANGUAGE


class WallText:
    """One language, resolved once per run and handed to the template as ``t``."""

    def __init__(self, language: str | None) -> None:
        self.language = normalise(language)
        self._strings = {**_catalog(BASE_LANGUAGE), **_catalog(self.language)}

    def __call__(self, key: str, **fields: object) -> str:
        """``{{ t("error.since", at=…) }}``.

        A key that exists nowhere renders as itself: visible on the wall, so it
        gets fixed, and never an exception.
        """
        template = self._strings.get(key, key)
        try:
            return template.format(**fields)
        except (KeyError, IndexError, ValueError):
            _LOGGER.warning("Placeholders of %r do not match %r", key, fields)
            return template

    def template(self, key: str) -> str:
        """The **unformatted** string, placeholders intact.

        For the one caller that has to recognise its own output again rather
        than produce it: the calendar strips a previously written ``— 80 Jahre``
        before computing a fresh count [P42], and the pattern for that is
        derived from ``"— {years} Jahre"``. Handing it the *formatted* text
        would build a pattern that only ever matches the sample number.
        """
        return self._strings.get(key, key)

    def moment(self, when: datetime) -> str:
        """Format a timestamp the way the language writes it."""
        return when.strftime(self("format.datetime"))
