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
RESULT_PUSH_OFF: Final = "push_off"            # rendered, push deliberately off
RESULT_RENDER_FAILED: Final = "render_failed"  # no image — aborted, nothing pushed

RUN_RESULTS: Final[tuple[str, ...]] = (
    RESULT_IDLE,
    RESULT_PUSHED,
    RESULT_UNCHANGED,
    RESULT_PUSH_FAILED,
    RESULT_PUSH_OFF,
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
# What is cooked tonight — its own narrow command rather than a flag on
# ``config/set`` [Festlegung 2026-08-31, Wolfgang]. The household picks the
# recipes the same way it switches the view; writing *configuration* stays
# administrator business. The difference is that this command builds its own
# patch from two validated fields, so the Paprika account sitting in the same
# store section cannot be reached through it.
WS_RECIPES_SELECT: Final = f"{DOMAIN}/recipes/select"
WS_GUESTS_SET: Final = f"{DOMAIN}/guests/set"
WS_GUESTS_BACKGROUNDS: Final = f"{DOMAIN}/guests/backgrounds"
# What the calendar page needs beyond the config document: how many entries each
# configured source actually answers with, and whether it answers at all. Read
# on demand rather than pushed into the status — it is a question somebody asks
# while setting the page up, not something the card shows every 15 seconds.
WS_CALENDAR_PROBE: Final = f"{DOMAIN}/calendar/probe"
# The deliberate press on the same page: pull the sources through
# ``homeassistant.update_entity``, count what they answer with, and ask for a
# render run so the wall catches up instead of waiting for the timed net.
WS_CALENDAR_SYNC: Final = f"{DOMAIN}/calendar/sync"
# Writing the year count back into the anniversary calendar [P42]. Its own
# command rather than a flag on ``calendar/sync``: that one only reads, this one
# changes somebody's real calendar on somebody else's server, and the two must
# never be one button by accident. Defaults to a dry run.
WS_CALENDAR_ANNIVERSARIES: Final = f"{DOMAIN}/calendar/anniversaries"

# --- Services (FSD §3.1) ------------------------------------------------------
SERVICE_GET_RENDER_DATA: Final = "get_render_data"
SERVICE_REPORT_RUN: Final = "report_run"
SERVICE_RENDER: Final = "render"
SERVICE_SET_VIEW: Final = "set_view"
SERVICE_SYNC_RECIPES: Final = "sync_recipes"
SERVICE_SET_GUESTS: Final = "set_guests"
SERVICE_SYNC_ANNIVERSARIES: Final = "sync_anniversaries"

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

# --- Calendar (FSD §8.1) ------------------------------------------------------
# How close together two source refreshes may sit. "Sync now" pulls the sources
# itself and then asks for a render run, and that run — undebounced, so within a
# second or two — would pull every published ICS a second time: one press, two
# fetches per source. The gap collapses that pair and nothing else; every other
# refresh comes from the timed net, 15 minutes apart.
CALENDAR_REFRESH_MIN_GAP_S: Final = 30

# --- Anniversary write-back (P42, Festlegung 2026-09-02) ----------------------
# When the daily run happens, and why it is a *time of day* rather than an
# interval. Measured at the source, not chosen by taste: ``caldav_writer``
# reads each entry's own **next** occurrence, searching from midnight of the
# current day. So an entry's count changes exactly once a year, at a date
# boundary — the night after its anniversary. An interval clock would drift
# across that boundary and answer differently at 23:50 than at 00:10; a fixed
# time of day cannot. A quarter past keeps it clear of the midnight crowd every
# other integration runs in, and a missed night costs nothing: the same number
# is still waiting the following night.
ANNIVERSARY_SYNC_HOUR: Final = 0
ANNIVERSARY_SYNC_MINUTE: Final = 15

# On by default [Festlegung 2026-09-02, Wolfgang]. The counter-argument was
# that this is the only place in the project that changes data on somebody
# else's server without being asked — but it only ever writes the number the
# wall is already showing, it writes nothing when nothing changed (measured
# 2026-09-02 at the real server: a second run is 0 changed, 0 written — it does
# read the calendar, roughly four seconds, but it cannot alter it), and an
# anniversary calendar with no year counts in it is exactly the state this
# feature exists to end. A switch that has to be found first would leave it
# there.
DEFAULT_ANNIVERSARY_WRITEBACK: Final = True

# --- Recipes (FSD §9) ---------------------------------------------------------
# How close together two Paprika syncs may sit. This is the replacement for a
# lock, not an addition to one: "Sync now" was administrator-only *because* the
# endpoint is documented to ban by IP (FSD §9.2), and opening it to the
# household [2026-08-31, Wolfgang] without putting something in its place would
# turn a button anybody can hold down into an IP ban. Short enough that "I just
# added a recipe" still works on the second press, far below the interval below,
# so a scheduled sync is never the one that gets skipped.
RECIPE_SYNC_MIN_GAP_S: Final = 60

# How often the collection is pulled from Paprika when nobody presses the
# button. Hours, because the constraint is a rate limit and not freshness: FSD
# §9.2 forbids a fetch per render run outright, and a household adds a recipe
# every few days, not every few minutes. The specification proposes 12 h; 24 h
# is the default here for the same reason it is a *setting* — the cheapest sync
# is the one that does not happen, and the panel's "Sync now" covers the moment
# somebody actually wants it now.
DEFAULT_RECIPE_SYNC_INTERVAL_H: Final = 24

# --- Calendar (FSD §8.1, kalenderkonzept.md Teil A) ---------------------------
# A source is a diary, a list of anniversaries or a list of public holidays,
# and the differences are not cosmetic: an anniversary carries a year count
# computed from its title, shows only its start time, and stays on the wall all
# day even when today's past entries are hidden — it is not an appointment
# anybody can be late for.
#
# A **holiday** [Festlegung P48, 2026-09-01] is the odd one out: its entries are
# not *of* the day but *about* it. They turn the day's badge red — the ground a
# Sunday wears — and stand in a line of their own above the appointments,
# without a time and without a colour bar. Which is why a holiday source carries
# no colour and is not in the legend: it belongs to nobody.
CALENDAR_KIND_EVENTS: Final = "events"
CALENDAR_KIND_BIRTHDAYS: Final = "birthdays"
CALENDAR_KIND_HOLIDAYS: Final = "holidays"
CALENDAR_KINDS: Final[tuple[str, ...]] = (
    CALENDAR_KIND_EVENTS,
    CALENDAR_KIND_BIRTHDAYS,
    CALENDAR_KIND_HOLIDAYS,
)

# The colour of the bar beside a line [Festlegung C8]. **Spectra primaries
# only**, minus white — the same rule as the guest greeting [P23]: any other
# value is reproduced by dithering it out of these six, and a 6 px bar of
# dithered near-blue is a speckle rather than a mark. White is left out because
# a white bar on a white page is no bar. The add-on's ``calendar_layout.COLORS``
# holds the hex values; tests/test_calendar_layout.py keeps the two in step.
CALENDAR_COLORS: Final[tuple[str, ...]] = ("blue", "green", "red", "yellow", "black")
DEFAULT_CALENDAR_COLOR: Final = "blue"

# Width of that bar. 2 px is the measured floor (FSD §7), 6 px was C8's figure —
# **12 px since P31** [2026-08-23, an der Wand entschieden]: at 1 m six pixels
# read as a mark next to the line, twelve read as the colour *of* the line,
# which is what the bar is for. Still adjustable, because the wall is the only
# place to judge it.
DEFAULT_CALENDAR_BAR_PX: Final = 12

# The **query** window, not the display window [Festlegung 2026-08-20]: the wall
# shows as many complete day blocks as fit. 30 days is the ceiling of the
# question, and birthdays get their own because one wants time to buy a present.
DEFAULT_CALENDAR_DAYS_EVENTS: Final = 30
DEFAULT_CALENDAR_DAYS_BIRTHDAYS: Final = 30

# Days without appointments are shown so the run of days has no holes
# [Festlegung 2026-08-20]. It costs about 126 px — roughly 1.5 appointments —
# which is why it can be switched off.
DEFAULT_CALENDAR_SHOW_EMPTY_DAYS: Final = True

# Whether an appointment that is already over still stands on the wall today.
# Off by default (the mockup's switch): at six in the evening the morning's
# stand-up is noise. Birthdays and all-day entries are exempt from the filter —
# a birthday vanishing at 09:16 would be a trap, not a setting.
DEFAULT_CALENDAR_SHOW_PAST_TODAY: Final = False

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

# The colour of the greeting [Festlegung P23]. **The six Spectra primaries and
# nothing else** — a colour off the palette is reproduced by dithering it out of
# these six, and on a glyph edge that comes out as a speckled outline rather
# than a tint. Same lesson as the grey hairline of phase 5.3 and the reason the
# recipe headings are palette blue and palette green.
#
# English tokens like every stored identifier; the labels live in the frontend
# catalogs, and ``tests/test_guest_layout.py`` holds this tuple, the add-on's
# ``COLORS``, the panel's picker and the catalogs together.
GUEST_COLORS: Final[tuple[str, ...]] = (
    "black",
    "white",
    "red",
    "yellow",
    "blue",
    "green",
)
DEFAULT_GUEST_COLOR: Final = "black"

# Tilt of the whole text block in degrees, positive clockwise. Bounded in the
# add-on (``guest_layout.ANGLE_LIMIT``): past 45° the block is more vertical
# than horizontal on a 16:9 canvas and every further degree only costs type
# size.
DEFAULT_GUEST_ANGLE: Final = 0

# The outline (FSD §8.4's third remedy, Festlegung P24). Off by default: a calm
# motif does not need it, and a seam always costs a script face a little of its
# elegance. The colour comes from ``GUEST_COLORS`` for the same reason the fill
# does — a seam is the thinnest feature on the page, and a dithered one would
# speckle exactly where it is meant to separate.
#
# The width is the **visible** one; the add-on doubles it for the CSS, because
# ``-webkit-text-stroke`` centres its stroke and the fill covers the inner half
# (``guest_layout.OUTLINE_CSS_FACTOR``).
DEFAULT_GUEST_OUTLINE: Final = False
DEFAULT_GUEST_OUTLINE_PX: Final = 8
DEFAULT_GUEST_OUTLINE_COLOR: Final = "white"

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
