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

# Entity platforms.
PLATFORMS: Final[list[Platform]] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
]

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

# --- WebSocket commands (FSD §3.1) --------------------------------------------
# The panel's and the card's only channel. Attributes are capped at 16 KB, so
# anything that grows — photo lists, later the recipe cache — travels here.
WS_CONFIG_GET: Final = f"{DOMAIN}/config/get"
WS_CONFIG_SET: Final = f"{DOMAIN}/config/set"
WS_STATUS: Final = f"{DOMAIN}/status"
WS_RENDER: Final = f"{DOMAIN}/render"
WS_SET_VIEW: Final = f"{DOMAIN}/set_view"
WS_PHOTOS_LIST: Final = f"{DOMAIN}/photos/list"
WS_DISPLAY_TEST: Final = f"{DOMAIN}/display/test"
WS_RECIPES_SEARCH: Final = f"{DOMAIN}/recipes/search"
WS_RECIPES_GET: Final = f"{DOMAIN}/recipes/get"
WS_RECIPES_SYNC: Final = f"{DOMAIN}/recipes/sync"
WS_GUESTS_SET: Final = f"{DOMAIN}/guests/set"
WS_GUESTS_BACKGROUNDS: Final = f"{DOMAIN}/guests/backgrounds"

# --- Services (FSD §3.1) ------------------------------------------------------
SERVICE_GET_RENDER_DATA: Final = "get_render_data"
SERVICE_REPORT_RUN: Final = "report_run"
SERVICE_RENDER: Final = "render"
SERVICE_SET_VIEW: Final = "set_view"
SERVICE_SYNC_RECIPES: Final = "sync_recipes"
SERVICE_SET_GUESTS: Final = "set_guests"

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

# The candidates the panel offers for sorting. Deliberately not "every view":
# FSD §5 defines an activity condition for exactly these five, and a candidate
# without a condition could never win a comparison (see ``resolve.py``).
SORTABLE_CANDIDATES: Final[tuple[str, ...]] = DEFAULT_PRIORITY

# --- Render cycle (FSD §6.1) --------------------------------------------------
# The timed net. Every 15 minutes rather than every 6 hours [Festlegung
# 2026-08-20]: it is what catches the changes that have no trigger of their own —
# an appointment moved on a phone, a new file in the photo folder — and it is
# cheap, because a run only pushes when the image hash changed (FSD §11). It is
# also the reason the card carries no refresh button.
RENDER_INTERVAL_MIN: Final = 15

# Debounce in the integration (FSD §6.1, Festlegung B6). Catches double clicks
# and a burst of config writes from the panel; the add-on's "last wins" queue
# handles the rest. Both, not either-or — a run takes ~10 s.
RENDER_DEBOUNCE_S: Final = 20

# How long an MDC probe answer counts as current. The add-on caches it too; this
# is the integration's own ceiling so a reload does not start with a blank sensor
# and a burst of handshakes.
DISPLAY_PROBE_INTERVAL_MIN: Final = 15

# --- Recipes (FSD §9) ---------------------------------------------------------
# How often the collection is pulled from Paprika when nobody presses the
# button. Hours, because the constraint is a rate limit and not freshness: FSD
# §9.2 forbids a fetch per render run outright, and a household adds a recipe
# every few days, not every few minutes. The specification proposes 12 h; 24 h
# is the default here for the same reason it is a *setting* — the cheapest sync
# is the one that does not happen, and the panel's "Sync now" covers the moment
# somebody actually wants it now.
DEFAULT_RECIPE_SYNC_INTERVAL_H: Final = 24

# --- Guests (FSD §8.4) --------------------------------------------------------
# The script faces the add-on ships (``addon-epaperengine/fonts/``). Listed here
# because the panel builds its dropdown from them and the store keeps the token;
# ``tests/test_guest_layout.py`` fails if this tuple, the add-on's ``FONTS`` and
# the panel's dropdown drift apart, or if a face loses its label.
#
# English tokens like every other stored identifier (FSD §3.0a) — the family
# names themselves are proper nouns and are not translated.
GUEST_FONT_DANCING_SCRIPT: Final = "dancing_script"
GUEST_FONT_CAVEAT: Final = "caveat"
GUEST_FONT_GREAT_VIBES: Final = "great_vibes"

GUEST_FONTS: Final[tuple[str, ...]] = (
    GUEST_FONT_DANCING_SCRIPT,
    GUEST_FONT_CAVEAT,
    GUEST_FONT_GREAT_VIBES,
)
DEFAULT_GUEST_FONT: Final = GUEST_FONT_DANCING_SCRIPT

# The type sizes of the mockup (11-wand-gaeste). Wishes, not commitments: a long
# name shrinks until it fits, which is what ``guest_layout.py`` in the add-on is
# for. Kept here as well because the panel offers them as the starting values.
DEFAULT_GUEST_NAME_PX: Final = 180
DEFAULT_GUEST_GREETING_PX: Final = 72

# Add-on endpoints (FSD §3.2). The base address is configuration
# (``display.renderer_url``) because the add-on may run on another host.
ADDON_RENDER_PATH: Final = "/render"
ADDON_DISPLAY_PATH: Final = "/display"
ADDON_HEALTH_PATH: Final = "/health"
# Refreshes the background cache and answers the list. Asked on demand rather
# than read out of the media tree: the panel has to offer a background *before*
# the first guest render has ever produced an index (FSD §8.4).
ADDON_BACKGROUNDS_PATH: Final = "/backgrounds"
DEFAULT_RENDERER_URL: Final = "http://homeassistant.local:8099"

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
# The recipe cache (FSD §9.1) — its own file rather than a section of the config
# document: it is written by the sync and not by the panel, it grows with the
# collection, and a config save must not have to carry a few hundred recipes
# through it.
STORE_RECIPES: Final = f"{DOMAIN}.recipes"
