"""Constants for the ePaperEngine integration.

The full specification lives in the development repo
(``gesamtsystem-fsd.md``); section references below point there.

Naming convention: **English is the base language across every subsystem**
(i18n concept §1/§3). That covers the *technical* identifiers too — domain,
entity object IDs, stored config keys and enum tokens are English; the German
wording lives in the translation catalogs and follows ``hass.language``.
"""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "epaperengine"

# Entity platforms. Empty for now — the six entities of FSD §3.1 arrive with the
# next build step; adding them here is all that is needed to switch them on.
PLATFORMS: Final[list[Platform]] = []

# --- Views (FSD §5) -----------------------------------------------------------
# Stored values and entity states — a contract, therefore stable English tokens.
# Every value needs a ``view.<value>`` entry in both frontend catalogs;
# tests/test_translations.py enforces that. Once the target-view sensor exists it
# additionally needs ``entity.sensor.target_view.state.<value>`` in all three HA
# catalogs (ENUM sensors show the raw token otherwise — in more-info, history,
# logbook and the automation editor, in every language).
VIEW_CALENDAR: Final = "calendar"
VIEW_RECIPES: Final = "recipes"
VIEW_PHOTOS: Final = "photos"
VIEW_GUESTS: Final = "guests"
VIEW_ERROR: Final = "error"

VIEWS: Final[tuple[str, ...]] = (
    VIEW_CALENDAR,
    VIEW_RECIPES,
    VIEW_PHOTOS,
    VIEW_GUESTS,
    VIEW_ERROR,
)

# --- Priority resolution (FSD §5) ---------------------------------------------
# Candidates of the ordered priority list. ``manual``/``schedule``/``fallback``
# are resolution *sources*, not views — they are listed alongside the views the
# user can pin, which is why this is its own token set.
CANDIDATE_MANUAL: Final = "manual"
CANDIDATE_SCHEDULE: Final = "schedule"
CANDIDATE_FALLBACK: Final = "fallback"

DEFAULT_PRIORITY: Final[tuple[str, ...]] = (
    CANDIDATE_MANUAL,
    VIEW_GUESTS,
    VIEW_RECIPES,
    CANDIDATE_SCHEDULE,
    CANDIDATE_FALLBACK,
)

# Manual override falls back to automatic after this many hours; 0 disables the
# fallback. Guests are exempt (FSD §5) — visitors stay for the weekend.
DEFAULT_MANUAL_TIMEOUT_H: Final = 4

# --- Frontend translation catalogs (i18n concept §6) --------------------------
# One shared catalog per language for the card *and* the panel, served from the
# integration directory over its own static path — no second copy under ``www/``
# and no stale-content risk when HACS unzips with old timestamps. Both
# front-ends fetch ``<url>/<lang>.json?v=<manifest version>`` (cache busting).
I18N_DIRNAME: Final = "frontend_i18n"
I18N_STATIC_URL: Final = f"/{DOMAIN}_i18n"
I18N_BASE_LANG: Final = "en"

# --- Sidebar panel and Lovelace card (FSD §3.1) -------------------------------
# Declared here so the URL contract is fixed from the start; registration
# happens in __init__.py once the JS files exist.
PANEL_URL_PATH: Final = "epaperengine"  # sidebar route (/epaperengine)
PANEL_TITLE: Final = "ePaperEngine"
PANEL_ICON: Final = "mdi:image-frame"
PANEL_FILENAME: Final = "epaperengine-panel.js"
PANEL_STATIC_URL: Final = f"/{DOMAIN}_panel/{PANEL_FILENAME}"
PANEL_CUSTOM_NAME: Final = "epaperengine-panel"  # custom element tag

CARD_FILENAME: Final = "epaperengine-card.js"
CARD_WWW_URL: Final = f"/local/{CARD_FILENAME}"

# --- Storage (FSD §4) ---------------------------------------------------------
STORAGE_VERSION: Final = 1
STORE_CONFIG: Final = f"{DOMAIN}.config"  # user configuration, panel-edited
STORE_STATE: Final = f"{DOMAIN}.state"    # last run, last push, manual override
