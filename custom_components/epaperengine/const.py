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

# Entity platforms. Phase 3 ships the two sensors that make a render run
# observable; the remaining entities of FSD §3.1 follow in phase 4.
PLATFORMS: Final[list[Platform]] = [Platform.SENSOR]

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

# --- Run results (FSD §11 / §12) ----------------------------------------------
# State of ``sensor.epaperengine_status`` — an ENUM, so every value needs an
# ``entity.sensor.status.state.<value>`` entry in all three HA catalogs, else
# more-info, history, logbook and the automation editor show the raw token in
# every language. tests/test_translations.py enforces that.
#
# The set follows straight from the specification: §11 makes "rendered but not
# pushed, because the image is unchanged" the *normal* outcome rather than an
# error, and §12 separates "the display did not take it" from "there was nothing
# to give it".
RESULT_IDLE: Final = "idle"                    # no run yet since installation
RESULT_PUSHED: Final = "pushed"                # rendered, image changed, pushed
RESULT_UNCHANGED: Final = "unchanged"          # rendered, same PNG hash, no push
RESULT_PUSH_FAILED: Final = "push_failed"      # rendered and served, display mute
RESULT_RENDER_FAILED: Final = "render_failed"  # no image — aborted, nothing pushed

RUN_RESULTS: Final[tuple[str, ...]] = (
    RESULT_IDLE,
    RESULT_PUSHED,
    RESULT_UNCHANGED,
    RESULT_PUSH_FAILED,
    RESULT_RENDER_FAILED,
)

# Dispatcher signal telling the entities that the run state changed. Format with
# the entry_id. Cheaper than a coordinator refresh for something that is pushed
# to us by the add-on rather than polled.
SIGNAL_STATE_UPDATED: Final = DOMAIN + "_state_updated_{}"

# --- Services (FSD §3.1) ------------------------------------------------------
SERVICE_GET_RENDER_DATA: Final = "get_render_data"
SERVICE_REPORT_RUN: Final = "report_run"

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
