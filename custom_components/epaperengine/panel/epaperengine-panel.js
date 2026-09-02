/**
 * ePaperEngine — sidebar panel (FSD §3.1).
 *
 * A build-free **custom** panel, not an iframe: Home Assistant hands `hass` in
 * and everything goes through the integration's WebSocket API
 * (custom_components/epaperengine/websocket_api.py). This is the *setting up*
 * surface — the daily glance lives in the Lovelace card.
 *
 * The card's rule "no control that only starts what happens anyway" does **not**
 * hold here: this is where things get tried out, and nobody wants to wait for
 * the next 15-minute net while doing so. Hence the two wall buttons
 * [Festlegung 2026-08-20]:
 *
 *   Update the wall      — a run right away; pushed only on a changed image hash
 *   Send the picture     — sends the current image **even when unchanged**,
 *   again                  stepping over the hash gate of FSD §11. A second
 *                          "force push" button on the display page would be the
 *                          same thing twice, so there is none.
 *
 * **Where the actions live** [Festlegung P36]: with their subject, not in the
 * header. The wall as a whole is the overview's subject, so both sit there,
 * beside the last-push line that is the reason anybody reaches for them. The
 * calendar sync sits on the calendar page, the recipe sync on the recipe page,
 * the background rescan on the guest page. The header carries no control at all
 * — it was explained by a `title` attribute, and no touch device shows one.
 *
 * Editing is draft-based per card: `_draft` is a working copy, committed on Save.
 */

const APP_NAME = "ePaperEngine";
const ICON = "mdi:image-frame"; // const.py PANEL_ICON

// Nav order. The three pages without a view yet stay visible on purpose: the
// navigation should not change shape when phase 5 lands.
// "Settings" is everything an administrator sets once and then forgets
// [Festlegung 2026-08-22]: the display, the Paprika account, the image paths.
// The view tabs keep what gets touched — the selection, the schedules, the
// cache state. It also draws the permission line in one place instead of half way
// down three pages.
const TABS = ["overview", "views", "calendar", "recipes", "photos", "guests", "settings"];
const TABS_PENDING = new Set([]);

const VIEWS = ["calendar", "recipes", "photos", "guests", "error"];
// What may be pinned by hand. ``error`` is a system state, not a choice.
const PINNABLE = ["calendar", "recipes", "photos", "guests"];
// The candidates the priority list may hold — the five FSD §5 defines an
// activity condition for. Anything else could never win a comparison.
const CANDIDATES = ["manual", "guests", "recipes", "schedule", "fallback"];

// Where the header's "Dashboard" goes back to. Both keys are written by the
// card (epaperengine-card.js) — two of them, because the panel is reachable two
// ways: the session key is the dashboard whose card sent us here on this trip,
// the local key the last dashboard that card was shown on at all, which is what
// is left when the panel was opened straight from the sidebar. Same mechanism as
// GardenESP; history.back() is no substitute, it has no answer for the sidebar
// route.
const RETURN_KEY = "epaperengine:return";
const DASHBOARD_KEY = "epaperengine:dashboard";

const POLL_MS = 15000;
const SEARCH_DEBOUNCE_MS = 250;

// How many recipes fit on the wall side by side (FSD §8.2 — three columns of
// 773 px), and how many characters each type size carries (FSD §7, measured at
// 1 m on the real panel).
const RECIPE_SLOTS = 3;

// The script faces the add-on ships (const.py GUEST_FONTS, and the FONTS table
// of the add-on's guest_layout.py). The three are kept in step by
// tests/test_guest_layout.py; the labels are the family names and are the same
// in every catalog, because a typeface is a proper noun.
const GUEST_FONTS = ["dancing_script", "caveat", "great_vibes"];

// The colour of the greeting (const.py GUEST_COLORS, and the COLORS table of
// the add-on's guest_layout.py). **The six Spectra primaries and nothing else**
// — every other value is reproduced by dithering it out of these, and on a
// glyph edge that is a speckled outline rather than a tint. The hex values here
// are only for the swatches in the picker; what is stored is the token.
const GUEST_COLORS = {
  black: "#000000",
  white: "#ffffff",
  red: "#dc1e1e",
  yellow: "#f0c81e",
  blue: "#1e3cb4",
  green: "#1e8c46",
};

// The colour of a calendar bar (const.py CALENDAR_COLORS, and the COLORS table
// of the add-on's calendar_layout.py). **Spectra primaries only, minus white**
// — the same rule the guest greeting follows [P23]; a 6 px bar in a dithered
// near-blue is a speckle, and a white one is no bar at all.
const CALENDAR_COLORS = {
  blue: "#1e3cb4",
  green: "#1e8c46",
  red: "#dc1e1e",
  yellow: "#f0c81e",
  black: "#000000",
};

// A source is a diary, a list of anniversaries or a list of public holidays
// (const.py CALENDAR_KINDS). "birthdays" adds the year count, the single start
// time and the exemption from the "hide today's past entries" filter;
// "holidays" turns the day's badge red and puts the name in a line of its own
// [P48] — which is why a holiday source has no colour to pick.
const CALENDAR_KINDS = ["events", "birthdays", "holidays"];
const CALENDAR_KIND_HOLIDAYS = "holidays";

// ---------------------------------------------------------------------------
// i18n — same mechanism and the same catalogs as the card (i18n concept §4/§7).
//
// The panel is the *editing* surface, so it carries one duty the card does not:
// every number it displays has to stay re-editable. Output goes through fmtNum,
// input through parseNum (both decimal separators) — never `parseFloat` on a
// string the user typed, that silently turns "1,5" into 1.
// ---------------------------------------------------------------------------
const I18N_URL = "/epaperengine_i18n"; // const.py I18N_STATIC_URL
const I18N_BASE_LANG = "en";
const VERSION = (() => {
  try {
    return new URL(import.meta.url).searchParams.get("v") || "0";
  } catch (e) {
    return "0";
  }
})();
const I18N_EMERGENCY = {
  "common.loading": "Loading…",
  "common.error": "Error: {msg}",
  "common.save": "Save",
  "common.saved": "Saved",
  "error.unknown": "Unknown error",
  "error.not_loaded": "ePaperEngine is not set up",
  "panel.tab.overview": "Overview",
  "panel.tab.views": "Views",
  "panel.tab.photos": "Photos",
  "panel.tab.display": "Display",
  "panel.action.render": "Update the wall",
  "panel.action.push": "Send the picture again",
  "panel.head.dashboard": "Dashboard",
};
const _i18nFetches = new Map();
let _i18n = { lang: null, cat: {}, base: {}, degraded: false };
const _fmt = { locale: I18N_BASE_LANG };

function i18nLang(hass) {
  return String((hass && hass.language) || I18N_BASE_LANG).split("-")[0];
}

function i18nFetch(lang) {
  if (!_i18nFetches.has(lang)) {
    _i18nFetches.set(
      lang,
      fetch(`${I18N_URL}/${lang}.json?v=${encodeURIComponent(VERSION)}`)
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    );
  }
  return _i18nFetches.get(lang);
}

async function i18nLoad(hass) {
  const lang = i18nLang(hass);
  _fmt.locale = (hass && hass.locale && hass.locale.language) || lang;
  if (_i18n.lang === lang) return;
  const [base, cat] = await Promise.all([
    i18nFetch(I18N_BASE_LANG),
    lang === I18N_BASE_LANG ? null : i18nFetch(lang),
  ]);
  _i18n = {
    lang,
    base: base || {},
    cat: cat || (lang === I18N_BASE_LANG ? base || {} : {}),
    degraded: !base,
  };
  if (_i18n.degraded) console.warn(`${APP_NAME}: no translation catalog loaded`);
}

function t(key, vars) {
  const s = _i18n.cat[key] ?? _i18n.base[key] ?? I18N_EMERGENCY[key] ?? humanizeKey(key);
  return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] == null ? m : String(vars[k]))) : s;
}

function humanizeKey(key) {
  const last = String(key).split(".").pop().replace(/_/g, " ");
  return last.charAt(0).toUpperCase() + last.slice(1);
}

function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

const viewLabel = (view) => (view ? t(`view.${view}`) : t("common.none"));
const candidateLabel = (c) => (VIEWS.includes(c) ? t(`view.${c}`) : t(`candidate.${c}`));

function fmtNum(value, opts) {
  const n = Number(value);
  if (!isFinite(n)) return "—";
  try {
    return new Intl.NumberFormat(_fmt.locale, opts).format(n);
  } catch (e) {
    return String(n);
  }
}

/** Counterpart to fmtNum: read a number the user typed, either separator. */
function parseNum(text) {
  if (text == null) return NaN;
  const s = String(text).trim().replace(/\s/g, "");
  if (!s) return NaN;
  const norm = /,\d{1,3}$/.test(s) ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  return Number(norm);
}

function fmtDateTime(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  if (isNaN(date)) return null;
  try {
    return new Intl.DateTimeFormat(_fmt.locale, {
      dateStyle: "short",
      timeStyle: "short",
    }).format(date);
  } catch (e) {
    return date.toISOString();
  }
}

function fmtTime(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  if (isNaN(date)) return null;
  try {
    return new Intl.DateTimeFormat(_fmt.locale, { hour: "2-digit", minute: "2-digit" }).format(date);
  } catch (e) {
    return date.toISOString().slice(11, 16);
  }
}

/**
 * Does the whole recipe fit — a tick or a cross, not a type size.
 *
 * "1: 28 px · 2: 26 px · 3: cut" was accurate and unreadable: the number a
 * household wants is not the type size, it is whether anything gets lost
 * [Festlegung 2026-08-22]. The size stays in the tooltip for whoever cares.
 *
 * The verdict itself comes from the integration, which runs the add-on's own
 * layout module (`recipe_layout.py`, kept byte-identical by publish.py). A rule
 * of thumb in this file would be a second, wronger model of the same thing —
 * the first version had one, and it called a recipe shortened that the wall was
 * rendering in full.
 */
const fitsAt = (fits, n) => !!(fits || {})[n] && (fits || {})[n] !== "cut";

function fitMark(fits, n) {
  const ok = fitsAt(fits, n);
  const colour = ok ? "var(--success-color,#43a047)" : "var(--error-color,#db4437)";
  return `<span style="color:${colour}">${n}&nbsp;${ok ? "✓" : "✗"}</span>`;
}

/** All three, as marks. Returns markup — the caller must not escape it. */
function fitTriple(fits) {
  return [1, 2, 3].map((n) => fitMark(fits, n)).join(" · ");
}

/** The long form, for the tooltip: "1 recipe(s): fits (28 px) · …". */
function fitTitle(fits) {
  return [1, 2, 3]
    .map((n) => {
      const verdict = fitsAt(fits, n)
        ? `${t("panel.recipes.fit.yes")} (${t("panel.recipes.fit.px", { n: (fits || {})[n] })})`
        : t("panel.recipes.fit.no");
      return t("panel.recipes.fit.detail", { n, verdict });
    })
    .join(" · ");
}

function fmtDuration(ms) {
  if (!isFinite(ms) || ms <= 0) return null;
  const minutes = Math.round(ms / 60000);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")} h`;
}

class EPaperEnginePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._narrow = false;
    this._tab = "overview";
    this._config = null;
    this._status = null;
    this._photos = null;
    this._backgrounds = null; // { total, backgrounds, folder } of the guest page
    this._calendar = null; // { counts, failed } of the last calendar probe
    this._calendarSync = null; // { at, on_wall } of the last "Sync now"
    this._calendarSyncing = false;
    this._recipes = null; // { hits, total, cache } of the last search
    this._picked = []; // the selected recipes in full, for the slot cards
    this._forecast = new Map(); // uid → {fit, chars}, filled from the searches
    this._query = "";
    this._syncedAt = null; // last sync the recipe page was drawn for
    this._syncing = false;
    this._searchTimer = null;
    this._draft = {};
    this._notice = null;
    this._error = null;
    this._probe = null; // result of the explicit "Test connection"
    this._previewUrl = null;
    this._previewFor = null; // the image hash the current signature was made for
    this._fullUrl = null; // signed full-size image, ready for the link
    this._built = false;
    this._timer = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
  }

  set narrow(value) {
    this._narrow = value;
  }

  connectedCallback() {
    this._timer = setInterval(() => this._refreshStatus(), POLL_MS);
    if (this._hass) this._load();
  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
    if (this._searchTimer) clearTimeout(this._searchTimer);
    this._searchTimer = null;
  }

  get isAdmin() {
    return !!(this._hass && this._hass.user && this._hass.user.is_admin);
  }

  async _call(message) {
    return this._hass.connection.sendMessagePromise(message);
  }

  async _load() {
    if (!this._hass) return;
    try {
      await i18nLoad(this._hass);
      const answer = await this._call({ type: "epaperengine/config/get" });
      this._config = answer.config;
      this._status = answer.status;
      this._draft = JSON.parse(JSON.stringify(answer.config));
      this._error = null;
      await this._signPreview();
    } catch (err) {
      this._error = this._message(err);
    }
    this._render();
  }

  /** Status only — the poll must not throw away what somebody is typing. */
  async _refreshStatus() {
    if (!this._hass || !this._config) return;
    try {
      this._status = await this._call({ type: "epaperengine/status" });
      // A new picture hangs on the wall: sign the preview again.
      //
      // ``preview_path`` is a **constant** path — always …/preview/current.jpg,
      // never a name that carries the version — so a repaint alone re-sets the
      // same src and shows the same picture. Nothing here would ever update it,
      // which is what the "reload preview" button used to paper over. The image
      // hash is the honest trigger: it changes exactly when the wall changed,
      // and a fresh signature is a different URL, so the browser has to fetch.
      //
      // The order holds: the add-on writes the media copy *before* it reports
      // the run, so a hash that reached Home Assistant is a file that exists.
      // An ``unchanged`` run leaves the hash alone (nothing to fetch), and a
      // failed push never writes the copy (the old preview is then the truth).
      if (((this._status || {}).last_push || {}).hash !== this._previewFor) {
        await this._signPreview();
      }
      // …and that promise only holds if the repaint is skipped while a field
      // has focus. Inputs are rebuilt from the draft on every render and the
      // draft is only read on Save, so a poll arriving mid-word would take the
      // word with it — a password or a search query most visibly. The header
      // goes one cycle stale instead, which nobody notices.
      const active = this.shadowRoot.activeElement;
      if (active && ["INPUT", "SELECT", "TEXTAREA"].includes(active.tagName)) return;
      // A sync that finished in the background (the timer, or the catch-up run
      // right after the account was saved) has to reach the open page — the
      // status carries the new count, but the hit list would sit there empty
      // and look broken.
      const synced = ((this._status || {}).recipes || {}).synced_at || null;
      if (this._tab === "recipes" && synced !== this._syncedAt) {
        this._syncedAt = synced;
        this._loadRecipes();
        return;
      }
      this._render();
    } catch (err) {
      /* a lost poll is not worth a message; the next one heals it */
    }
  }

  _message(err) {
    if (!err) return t("error.unknown");
    if (err.code === "unauthorized") return t("error.no_admin");
    if (err.code === "not_loaded") return t("error.not_loaded");
    return err.message || t("error.code", { code: err.code || "?" });
  }

  /**
   * ``media`` is authenticated and an `<img>` carries no bearer token, so the
   * path is signed just before use (FSD §15, measured 2026-08-21). The panel
   * signs rather than the integration: a signature expires, and the surface that
   * keeps it on screen is the one that has to renew it.
   */
  async _sign(path, expires = 3600) {
    if (!path) return null;
    try {
      const signed = await this._call({ type: "auth/sign_path", path, expires });
      return signed && signed.path ? signed.path : null;
    } catch (err) {
      return null;
    }
  }

  async _signPreview() {
    const status = this._status || {};
    // Remembered before the await, so a run that finishes mid-signature is not
    // mistaken for the one this signature belongs to.
    this._previewFor = (status.last_push || {}).hash || null;
    this._previewUrl = await this._sign(status.preview_path);
    // Signed **here**, not when the link is clicked. A `window.open()` that
    // happens after an `await` has lost the user gesture that permitted it, and
    // every current browser drops it into the popup blocker without a word —
    // which is exactly how "Open full size" did nothing at all. A real anchor
    // with an href needs no permission.
    this._fullUrl = await this._sign(status.wall_path);
  }

  // --- actions --------------------------------------------------------------
  async _save(sections) {
    const patch = {};
    for (const section of sections) patch[section] = this._draft[section];
    await this._commit({ type: "epaperengine/config/set", config: patch });
  }

  /**
   * Send one write command and adopt whatever it answered.
   *
   * Two commands share this: the administrator's config/set and the
   * household's recipes/select. They answer the same shape deliberately, so
   * what the page looks like after saving does not depend on who saved. The
   * configuration that comes back is redacted for whoever asked, which is why
   * the draft is rebuilt from the answer rather than from what was sent.
   */
  async _commit(message) {
    try {
      const answer = await this._call(message);
      this._config = answer.config;
      this._status = answer.status;
      this._draft = JSON.parse(JSON.stringify(answer.config));
      this._notice = t("common.saved");
      this._error = null;
    } catch (err) {
      this._error = this._message(err);
    }
    this._render();
    setTimeout(() => {
      this._notice = null;
      this._render();
    }, 2500);
  }

  async _render_now(force) {
    try {
      await this._call({ type: "epaperengine/render", force: !!force });
      this._notice = t("panel.action.queued");
      this._error = null;
    } catch (err) {
      this._error = this._message(err);
    }
    this._render();
    setTimeout(() => {
      this._notice = null;
      this._render();
    }, 2500);
  }

  async _setView(view) {
    try {
      this._status = await this._call({ type: "epaperengine/set_view", view });
      this._error = null;
    } catch (err) {
      this._error = this._message(err);
    }
    this._render();
  }

  async _testDisplay() {
    this._probe = { pending: true };
    this._render();
    try {
      this._probe = await this._call({ type: "epaperengine/display/test" });
      this._status = await this._call({ type: "epaperengine/status" });
    } catch (err) {
      this._probe = { reachable: false, error: this._message(err) };
    }
    this._render();
  }

  async _loadPhotos() {
    try {
      const answer = await this._call({ type: "epaperengine/photos/list" });
      // Thumbnails are signed one by one; the list is short (a few hundred at
      // 15 KB) and one signature per file is what the media view expects.
      answer.photos = await Promise.all(
        answer.photos.map(async (photo) => ({ ...photo, url: await this._sign(photo.thumb) })),
      );
      this._photos = answer;
    } catch (err) {
      this._photos = { total: 0, photos: [], error: this._message(err) };
    }
    this._render();
  }

  // --- guests (FSD §8.4) ----------------------------------------------------
  /**
   * The backgrounds, listed by the add-on.
   *
   * The add-on *rescans the folder* for this, rather than the integration
   * reading whatever a previous run left behind: a picture has to be pickable
   * before the first guest render has ever happened, and only the add-on can
   * crop, hash and thumbnail one. Slow enough to say so — a folder full of
   * 20-megapixel photographs is cropped here, once.
   */
  async _loadBackgrounds() {
    this._backgrounds = this._backgrounds || { loading: true, backgrounds: [] };
    try {
      const answer = await this._call({ type: "epaperengine/guests/backgrounds" });
      answer.backgrounds = await Promise.all(
        answer.backgrounds.map(async (item) => ({ ...item, url: await this._sign(item.thumb) })),
      );
      this._backgrounds = answer;
    } catch (err) {
      this._backgrounds = { total: 0, backgrounds: [], error: this._message(err) };
    }
    this._render();
  }

  // --- calendar (FSD §8.1) --------------------------------------------------
  /**
   * How many entries each configured source answers with, and which do not.
   *
   * The one thing the configuration document cannot say: whether the entity
   * behind ``calendar.wolfgang`` is alive. Measured on HA 2026.8.2 — a
   * non-existent entity is dropped from a collective ``get_events`` **without
   * an error**, so "no number here" is the only signal there is.
   */
  async _probeCalendar() {
    this._calendar = this._calendar || { loading: true };
    try {
      this._calendar = await this._call({ type: "epaperengine/calendar/probe" });
    } catch (err) {
      this._calendar = { counts: {}, failed: {}, error: this._message(err) };
    }
    this._calendarSync = null; // the numbers no longer come from a source pull
    this._render();
  }

  /**
   * "Sync now" — the deliberate press, as opposed to "recount".
   *
   * Three things in one because they are one intention: pull every source
   * through homeassistant.update_entity, count what they answer with, and ask
   * for a render run. Without the last step a calendar somebody just corrected
   * on their phone still waits up to 15 minutes for the timed net.
   *
   * The run is only queued, never awaited — the add-on answers 202 and works
   * on. What the answer does carry is on_wall: a wall showing photos takes the
   * fresh data and shows none of it, and saying so beats looking broken.
   */
  async _syncCalendar() {
    this._calendarSyncing = true;
    this._render();
    try {
      const answer = await this._call({ type: "epaperengine/calendar/sync" });
      this._calendar = answer;
      this._calendarSync = { at: answer.at, on_wall: !!answer.on_wall };
      this._error = null;
    } catch (err) {
      this._calendarSync = null;
      this._error = this._message(err);
    }
    this._calendarSyncing = false;
    this._render();
    await this._refreshStatus();
  }

  /**
   * "Write back now" - the year count into the anniversary calendars [P42].
   *
   * No dry run in front of it [Festlegung 2026-09-02, Wolfgang]. The transport
   * still defaults to one and the service still offers it, but a preview step
   * here would ask a question nobody can answer better than the operation
   * itself: it is idempotent, it writes only the number the wall is already
   * showing, and it changes nothing when nothing changed. The nightly timer
   * does the same thing at 00:15 without asking anybody.
   *
   * What the answer is for is the line underneath: how many entries were seen,
   * how many were rewritten, and which source refused.
   */
  async _writeAnniversaries() {
    this._annivRunning = true;
    this._render();
    try {
      const answer = await this._call({
        type: "epaperengine/calendar/anniversaries",
        dry_run: false,
      });
      this._anniv = answer;
      this._error = null;
    } catch (err) {
      this._anniv = null;
      this._error = this._message(err);
    }
    this._annivRunning = false;
    this._render();
    await this._refreshStatus();
  }

  /** Switch guest mode on or off. State, not configuration — no Save button. */
  async _setGuests(active) {
    try {
      this._status = await this._call({ type: "epaperengine/guests/set", active: !!active });
      this._error = null;
    } catch (err) {
      this._error = this._message(err);
    }
    this._render();
  }

  /**
   * Pick a background, or clear it.
   *
   * Committed straight away, like the recipe selection and for the same reason:
   * it is a decision about what hangs on the wall tonight, it triggers a render
   * (FSD §6.1), and a draft nobody saved would mean clicking a picture and
   * staring at an unchanged display. The text fields of the page are collected
   * along with it — somebody who typed a name and then chose a picture meant
   * both.
   */
  async _pickBackground(digest) {
    this._collect();
    this._draft.guests.background = digest || null;
    await this._save(["guests"]);
  }

  // --- recipes (FSD §9) -----------------------------------------------------
  /** Search the cache and fetch the picked recipes — one screen, two calls. */
  async _loadRecipes() {
    try {
      const [found, picked] = await Promise.all([
        this._call({ type: "epaperengine/recipes/search", query: this._query }),
        this._call({
          type: "epaperengine/recipes/get",
          uids: [...((this._draft.recipes || {}).selection || [])],
        }),
      ]);
      this._recipes = found;
      this._picked = picked.recipes || [];
      this._syncedAt = (found.cache || {}).synced_at || null;
      this._rememberForecasts(found.hits);
      this._error = null;
    } catch (err) {
      this._recipes = { hits: [], total: 0, error: this._message(err) };
    }
    this._render();
  }

  /**
   * Typing searches, but not on every keystroke: the round trip is local and
   * cheap, the re-render is not — it would fight the cursor in the very field
   * being typed into.
   */
  _searchLater(query) {
    this._query = query;
    if (this._searchTimer) clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(async () => {
      this._searchTimer = null;
      try {
        this._recipes = await this._call({
          type: "epaperengine/recipes/search",
          query: this._query,
        });
      } catch (err) {
        this._recipes = { hits: [], total: 0, error: this._message(err) };
      }
      this._rememberForecasts(this._recipes.hits);
      this._renderHits();
    }, SEARCH_DEBOUNCE_MS);
  }

  /**
   * Keep the verdict for every recipe the search has ever shown.
   *
   * A picked recipe drops out of the hit list as soon as the query moves on,
   * and its slot still has to say whether it will be shortened. Cheap: one
   * small object per recipe, thrown away with the page.
   */
  _rememberForecasts(hits) {
    for (const hit of hits || []) this._forecast.set(hit.uid, { fits: hit.fits, chars: hit.chars });
  }

  /** Repaint the hit list alone, so the search field keeps focus and caret. */
  _renderHits() {
    const list = this.shadowRoot.querySelector("#hits");
    if (!list) return this._render();
    list.innerHTML = this._hitRows();
    this._wireHits();
  }

  async _syncRecipes() {
    this._syncing = true;
    this._render();
    try {
      const status = await this._call({ type: "epaperengine/recipes/sync" });
      this._syncing = false;
      this._error = status.error ? t("panel.recipes.error.sync", { msg: status.error }) : null;
      if (!status.error) {
        // A press inside the rate gap fetched nothing, and saying "0 fetched,
        // 0 removed" would read like an empty collection rather than a button
        // pressed twice. The gap is what replaced the administrator lock here.
        this._notice = status.skipped
          ? t("panel.recipes.sync.skipped")
          : t("panel.recipes.sync.done", {
              count: fmtNum(status.fetched ?? 0),
              removed: fmtNum(status.removed ?? 0),
            });
        setTimeout(() => {
          this._notice = null;
          this._render();
        }, 4000);
      }
    } catch (err) {
      this._syncing = false;
      this._error = this._message(err);
    }
    await this._refreshStatus();
    await this._loadRecipes();
  }

  _pick(uid) {
    const selection = [...((this._draft.recipes || {}).selection || [])];
    if (selection.includes(uid) || selection.length >= RECIPE_SLOTS) return;
    this._draft.recipes.selection = [...selection, uid];
    this._saveSelection();
  }

  _unpick(uid) {
    this._draft.recipes.selection = ((this._draft.recipes || {}).selection || []).filter(
      (entry) => entry !== uid,
    );
    this._saveSelection();
  }

  _moveSlot(index, direction) {
    const selection = [...((this._draft.recipes || {}).selection || [])];
    const to = index + direction;
    if (to < 0 || to >= selection.length) return;
    [selection[index], selection[to]] = [selection[to], selection[index]];
    this._draft.recipes.selection = selection;
    this._saveSelection();
  }

  /**
   * The selection saves itself — no Save button on that card.
   *
   * It is the one setting on this page that is a *decision about tonight*
   * rather than configuration, it is two clicks away from being undone, and
   * FSD §9.3 says setting it triggers a render run. A draft nobody committed
   * would mean picking a recipe and staring at an unchanged wall.
   *
   * Its own command since 2026-08-31, not config/set: the whole household may
   * choose what is cooked, and config/set is administrator-only because the
   * display PIN and the Paprika account go through it. Only the two fields
   * below are sent, and the server builds the patch from them.
   */
  async _saveSelection() {
    const recipes = this._draft.recipes || {};
    await this._commit({
      type: "epaperengine/recipes/select",
      selection: [...(recipes.selection || [])],
      servings: { ...(recipes.servings || {}) },
    });
    await this._loadRecipes();
  }

  _go(tab) {
    this._tab = tab;
    this._probe = null;
    if (tab === "photos" && !this._photos) this._loadPhotos();
    // The background list is an administrator command (it rescans the folder),
    // so a household member is not sent into a guaranteed "unauthorized".
    if (tab === "guests" && !this._backgrounds && this.isAdmin) this._loadBackgrounds();
    if (tab === "recipes") this._loadRecipes();
    // Admin-only command, so a household member is not sent into a guaranteed
    // "unauthorized" just by opening the page.
    if (tab === "calendar" && this.isAdmin) this._probeCalendar();
    this._render();
  }

  // --- rendering ------------------------------------------------------------
  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; height: 100%; background: var(--primary-background-color); }
        .wrap { display: flex; flex-direction: column; height: 100%; }
        header {
          display: flex; align-items: center; gap: 12px; padding: 12px 20px;
          background: var(--card-background-color);
          border-bottom: 1px solid var(--divider-color); flex: none; flex-wrap: wrap;
        }
        header .title { font-size: 1.25rem; font-weight: 700; flex: 1; }
        header button.back { flex: none; }
        .status-dot { display: inline-flex; align-items: center; gap: 6px;
                      color: var(--secondary-text-color); font-size: 0.87rem; }
        .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--disabled-text-color, #9e9e9e); }
        .dot.ok { background: var(--success-color, #43a047); }
        .dot.bad { background: var(--error-color, #db4437); }
        .dot.warn { background: var(--warning-color, #ff9800); }
        button, .btn {
          font: inherit; cursor: pointer; border-radius: 6px; padding: 8px 14px;
          border: 1px solid var(--primary-color); background: var(--card-background-color);
          color: var(--primary-color);
        }
        /* "btn" is for the one control that has to be a real link: an anchor
           opens a new tab from the click itself, where a scripted window.open
           after an await is blocked.
           NO BACKTICKS IN HERE — this block lives inside a template literal,
           and a pair of them turns the rest into a tagged template call that
           throws at runtime while node --check stays silent. */
        .btn { display: inline-block; text-decoration: none; }
        button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        button.plain, .btn.plain { border-color: var(--divider-color); color: var(--primary-text-color); }
        button.small { padding: 4px 8px; font-size: 0.85rem; }
        button:disabled { opacity: 0.5; cursor: default; }
        .main { display: flex; flex: 1; min-height: 0; }
        nav {
          width: 200px; flex: none; padding: 12px 0;
          background: var(--card-background-color);
          border-right: 1px solid var(--divider-color); overflow-y: auto;
        }
        nav a {
          display: block; padding: 10px 20px; cursor: pointer;
          color: var(--primary-text-color); text-decoration: none;
        }
        nav a.on { background: var(--secondary-background-color); color: var(--primary-color); font-weight: 600;
                   border-left: 3px solid var(--primary-color); padding-left: 17px; }
        nav a.pending { color: var(--secondary-text-color); }
        .content { flex: 1; overflow-y: auto; padding: 20px; }
        /* One column of cards beside the nav, never several: the nav is column
           one, the cards are column two. An auto-fit grid used to spread them
           over the whole desktop width, which put unrelated cards side by side
           and made every line as wide as the screen. The cap keeps the column
           readable; wide content (thumbnails, chips) still fills it. */
        .grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px;
                align-items: start; max-width: 800px; }
        .card {
          background: var(--card-background-color); border-radius: 12px; padding: 16px;
          box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,0.12));
        }
        .card h2 { margin: 0 0 2px; font-size: 1.05rem; }
        .card .hint { color: var(--secondary-text-color); font-size: 0.85rem; margin-bottom: 12px; }
        label { display: block; font-size: 0.8rem; color: var(--secondary-text-color); margin: 10px 0 4px; }
        input, select {
          width: 100%; box-sizing: border-box; padding: 8px 10px; font: inherit;
          border: 1px solid var(--divider-color); border-radius: 6px;
          background: var(--card-background-color); color: var(--primary-text-color);
        }
        .inline { display: flex; gap: 10px; align-items: flex-end; }
        .inline > * { flex: 1; }
        .inline .unit { flex: none; padding-bottom: 9px; color: var(--secondary-text-color); font-size: 0.85rem; }
        .actions { margin-top: 14px; display: flex; gap: 8px; flex-wrap: wrap; }
        table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
        th { text-align: left; font-size: 0.72rem; letter-spacing: 0.05em; text-transform: uppercase;
             color: var(--secondary-text-color); padding: 4px 6px; font-weight: 600; }
        td { padding: 6px; border-top: 1px solid var(--divider-color); vertical-align: middle; }
        .kv { display: grid; grid-template-columns: 40% 1fr; gap: 6px 12px; font-size: 0.9rem; }
        .kv .k { color: var(--secondary-text-color); }
        .rank { display: flex; flex-direction: column; }
        .sortrow {
          display: flex; align-items: center; gap: 10px; padding: 10px 12px; margin-bottom: 8px;
          border: 1px solid var(--divider-color); border-radius: 8px;
        }
        .sortrow.on { border-color: var(--primary-color); background: var(--secondary-background-color); }
        .sortrow .grow { flex: 1; }
        .sortrow .name { font-weight: 600; }
        .sortrow .why { color: var(--secondary-text-color); font-size: 0.82rem; }
        .sortrow .badge { color: var(--primary-color); font-size: 0.82rem; font-weight: 600; }
        .servings { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; }
        .servings label { margin: 0; }
        .servings input { width: 70px; padding: 4px 6px; }
        .note {
          border-left: 4px solid var(--primary-color); background: var(--secondary-background-color);
          padding: 8px 12px; border-radius: 4px; font-size: 0.85rem; margin-top: 12px;
        }
        .note.warn { border-left-color: var(--warning-color, #ff9800); }
        .note.bad { border-left-color: var(--error-color, #db4437); }
        .chips { display: flex; flex-wrap: wrap; gap: 8px; }
        .chip {
          border: 1px solid var(--divider-color); border-radius: 16px; padding: 5px 14px;
          background: var(--card-background-color); color: var(--primary-text-color);
          font: inherit; font-size: 0.87rem; cursor: pointer;
        }
        .chip.on { border-color: var(--primary-color); color: var(--primary-color); font-weight: 600; }
        .thumbs { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
        .thumb img { width: 100%; border-radius: 6px; display: block; aspect-ratio: 16/9;
                     object-fit: cover; background: var(--secondary-background-color); }
        .thumb .cap { font-size: 0.75rem; color: var(--secondary-text-color);
                      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .thumb.pick { cursor: pointer; padding: 4px; border: 2px solid transparent; border-radius: 10px; }
        .thumb.pick.on { border-color: var(--primary-color); }
        .thumb.blank { display: flex; align-items: center; justify-content: center;
                       aspect-ratio: 16/9; border-radius: 6px; font-size: 0.8rem;
                       text-align: center; color: var(--secondary-text-color);
                       background: var(--secondary-background-color); }
        .row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .swatches { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
        .swatch { display: inline-flex; align-items: center; gap: 7px; padding: 5px 12px;
                  border-radius: 16px; border: 1px solid var(--divider-color);
                  background: var(--card-background-color); color: var(--primary-text-color);
                  font: inherit; font-size: 0.85rem; cursor: pointer; }
        .swatch.on { border-color: var(--primary-color); color: var(--primary-color); font-weight: 600; }
        .swatch span { width: 16px; height: 16px; border-radius: 50%;
                       border: 1px solid var(--divider-color); display: inline-block; }
        .row label { margin: 0; }
        .preview { width: 100%; border-radius: 8px; display: block; aspect-ratio: 16/9;
                   object-fit: contain; background: var(--secondary-background-color); }
        .muted { color: var(--secondary-text-color); font-size: 0.85rem; }
        @media (max-width: 700px) {
          .main { flex-direction: column; }
          nav { width: auto; display: flex; overflow-x: auto; border-right: none;
                border-bottom: 1px solid var(--divider-color); }
          nav a.on { border-left: none; padding-left: 20px; border-bottom: 3px solid var(--primary-color); }
        }
      </style>
      <div class="wrap">
        <header></header>
        <div class="main"><nav></nav><div class="content"></div></div>
      </div>
    `;
    this._built = true;
  }

  _render() {
    if (!this._built) this._build();
    const root = this.shadowRoot;
    root.querySelector("header").innerHTML = this._header();
    root.querySelector("nav").innerHTML = this._nav();
    root.querySelector(".content").innerHTML = this._page();
    this._wire();
  }

  /**
   * Icon, name, whether the display answers — and the one way back out.
   *
   * **No wall controls.** "Render now" and "Push now" used to sit here; they are
   * gone (P36, see the file header). "Dashboard" is not one of them: it acts on
   * the browser, not on the wall, and it is the only thing in this panel that
   * cannot live with its subject — its subject is somewhere else. Without it the
   * panel is a dead end whenever the HA sidebar is collapsed or narrow.
   *
   * "Render now" and "Push now" used to sit here, on every page, explained by a
   * title attribute — which no touch device ever shows. They are rare acts, not
   * everyday ones: saving in this panel already redraws the wall, and the timed
   * net does it every 15 minutes anyway. Both now live on the overview, next to
   * the last-push line that is the reason anybody reaches for them, with the
   * explanation written out where it can be read.
   */
  _header() {
    const display = (this._status && this._status.display) || {};
    let cls = "";
    let label = t("panel.display.unknown");
    if (display.reachable) {
      cls = "ok";
      label = t("panel.display.reachable");
    } else if (Object.keys(display).length) {
      cls = "bad";
      label = t("panel.display.unreachable");
    }
    return `
      <ha-icon icon="${ICON}"></ha-icon>
      <div class="title">${esc(APP_NAME)}</div>
      <span class="status-dot"><span class="dot ${cls}"></span>${esc(label)}</span>
      <button id="to-dashboard" class="plain back" title="${esc(t("panel.head.dashboard_title"))}">${esc(t("panel.head.dashboard"))}</button>
    `;
  }

  /**
   * Leave the panel for the dashboard the visitor came from.
   *
   * Deliberately a full navigation, not the card's pushState/location-changed
   * hop: this is the escape hatch, and it has to work from a cold panel where no
   * router state was ever built up. Reading storage is wrapped because a browser
   * in private mode throws on the *getter*, not on the write.
   */
  _toDashboard() {
    let target = null;
    try {
      target = sessionStorage.getItem(RETURN_KEY) || localStorage.getItem(DASHBOARD_KEY);
    } catch (err) {
      /* private mode — fall through to the default dashboard */
    }
    location.href = target || "/";
  }

  _nav() {
    return TABS.map(
      (tab) =>
        `<a data-tab="${tab}" class="${tab === this._tab ? "on" : ""} ${
          TABS_PENDING.has(tab) ? "pending" : ""
        }">${esc(t(`panel.tab.${tab}`))}</a>`,
    ).join("");
  }

  _banner() {
    if (this._error) return `<div class="note bad">${esc(t("common.error", { msg: this._error }))}</div>`;
    if (this._notice) return `<div class="note">${esc(this._notice)}</div>`;
    return "";
  }

  _page() {
    if (!this._config) {
      return `<div class="card">${esc(this._error || t("common.loading"))}</div>`;
    }
    if (TABS_PENDING.has(this._tab)) {
      return `${this._banner()}<div class="card"><h2>${esc(t(`panel.tab.${this._tab}`))}</h2>
        <div class="hint">${esc(t("panel.tab.soon"))}</div></div>`;
    }
    const body = {
      overview: () => this._pageOverview(),
      views: () => this._pageViews(),
      calendar: () => this._pageCalendar(),
      recipes: () => this._pageRecipes(),
      photos: () => this._pagePhotos(),
      guests: () => this._pageGuests(),
      settings: () => this._pageSettings(),
    }[this._tab];
    return this._banner() + `<div class="grid">${body ? body() : ""}</div>`;
  }

  // --- page: overview -------------------------------------------------------
  _pageOverview() {
    const status = this._status || {};
    const target = status.target || {};
    const manual = status.manual;
    const push = status.last_push || {};
    const run = status.last_run || {};

    const because = this._becauseLine(status);
    const since = fmtTime((manual && manual.at) || push.at);
    const left = manual && manual.until ? fmtDuration(new Date(manual.until) - new Date()) : null;

    const chips = [
      `<button class="chip ${manual ? "" : "on"}" data-view="">${esc(t("card.chip.auto"))}</button>`,
      ...PINNABLE.map(
        (view) =>
          `<button class="chip ${manual && manual.view === view ? "on" : ""}" data-view="${view}">${esc(
            viewLabel(view),
          )}</button>`,
      ),
    ].join("");

    const manualNote = manual
      ? `<div class="note warn">${esc(
          left ? t("card.override.until", { duration: left }) : t("panel.overview.manual.open"),
        )}</div>`
      : "";

    const preview = this._previewUrl
      ? `<img class="preview" src="${esc(this._previewUrl)}" alt="${esc(viewLabel(target.view))}">`
      : `<div class="preview"></div><div class="muted">${esc(t("panel.overview.preview.none"))}</div>`;
    const fullLink = this._fullUrl
      ? `<a class="btn plain" href="${esc(this._fullUrl)}" target="_blank" rel="noopener">${esc(
          t("panel.overview.preview.full"),
        )}</a>`
      : "";

    return `
      <div class="card">
        <h2>${esc(t("panel.overview.current"))}</h2>
        <div class="hint">${esc(t("panel.overview.shows"))}</div>
        <div style="font-size:1.6rem;font-weight:700;color:var(--primary-color)">${esc(viewLabel(target.view))}</div>
        <div class="kv" style="margin-top:12px">
          <div class="k">${esc(t("panel.overview.because"))}</div><div>${esc(because)}</div>
          <div class="k">${esc(t("panel.overview.since"))}</div><div>${esc(since || t("common.unknown"))}</div>
          <div class="k">${esc(t("card.next_change"))}</div><div>${esc(fmtDateTime(status.next_change) || t("common.none"))}</div>
        </div>
      </div>

      <div class="card">
        <h2>${esc(t("panel.overview.push"))}</h2>
        <div class="hint">${esc(t("panel.overview.run"))}: ${esc(t(`result.${status.result || "idle"}`))}</div>
        <div class="kv">
          <div class="k">${esc(t("card.last_push"))}</div>
          <div>${esc(fmtDateTime(push.at) || t("panel.overview.push.none"))}</div>
          <div class="k">${esc(t("panel.overview.push.hash"))}</div>
          <div style="font-family:monospace;font-size:0.8rem">${esc(push.hash ? push.hash.slice(0, 12) + "…" : t("common.none"))}</div>
          <div class="k">${esc(t("panel.overview.run"))}</div>
          <div>${esc(fmtDateTime(run.at) || t("common.none"))}</div>
        </div>
        ${run.error ? `<div class="note bad">${esc(run.error)}</div>` : ""}
        ${run.warning ? `<div class="note warn">${esc(run.warning)}</div>` : ""}
        ${status.addon_error ? `<div class="note bad">${esc(status.addon_error)}</div>` : ""}
      </div>

      <div class="card">
        <h2>${esc(t("panel.overview.actions"))}</h2>
        <div class="hint">${esc(t("panel.overview.actions.hint"))}</div>
        <div class="actions"><button class="primary" id="do-render">${esc(
          t("panel.action.render"),
        )}</button></div>
        <div class="muted">${esc(t("panel.action.render.hint"))}</div>
        <div class="actions"><button class="plain" id="do-push">${esc(
          t("panel.action.push"),
        )}</button></div>
        <div class="muted">${esc(t("panel.action.push.hint"))}</div>
      </div>

      <div class="card">
        <h2>${esc(t("panel.overview.manual"))}</h2>
        <div class="hint">${esc(t("panel.overview.manual.hint"))}</div>
        <div class="chips">${chips}</div>
        ${manualNote}
        ${manual ? `<div class="actions"><button class="plain" id="to-auto">${esc(t("panel.overview.manual.auto"))}</button></div>` : ""}
      </div>

      <div class="card">
        <h2>${esc(t("panel.overview.preview"))}</h2>
        <div class="hint">${esc(t("panel.overview.preview.hint"))}</div>
        ${preview}
        ${fullLink ? `<div class="actions">${fullLink}</div>` : ""}
      </div>
    `;
  }

  _becauseLine(status) {
    const target = status.target || {};
    switch (target.source) {
      case "manual": {
        const until = fmtTime(target.until);
        return until ? t("card.because.manual", { time: until }) : t("card.because.manual_open");
      }
      case "schedule":
        return t("card.because.schedule", {
          name: String(target.schedule_entity || "").split(".").pop(),
          rank: target.rank ?? "—",
        });
      case "guests":
        return t("card.because.guests");
      case "recipes":
        return t("card.because.recipes", { count: target.selected ?? 0 });
      default:
        return t("card.because.fallback");
    }
  }

  // --- page: views ----------------------------------------------------------
  _pageViews() {
    const views = this._draft.views || {};
    const priority = (views.priority || []).filter((c) => CANDIDATES.includes(c));
    const activeSource = ((this._status || {}).target || {}).source;

    const rows = priority
      .map((candidate, index) => {
        // Every candidate carries its own one-liner ("as long as guest mode is
        // on"); the priority list is useless without them.
        const hintKey = `candidate.${candidate}.hint`;
        return `<div class="sortrow ${candidate === activeSource ? "on" : ""}">
          <div class="grow">
            <div class="name">${esc(candidateLabel(candidate))}</div>
            <div class="why">${esc(t(hintKey))}</div>
          </div>
          ${candidate === activeSource ? `<span class="badge">${esc(t("candidate.active"))}</span>` : ""}
          <div class="rank">
            <button class="plain small" data-move="up" data-index="${index}" title="${esc(t("panel.views.up"))}" ${index === 0 ? "disabled" : ""}>▲</button>
            <button class="plain small" data-move="down" data-index="${index}" title="${esc(t("panel.views.down"))}" ${index === priority.length - 1 ? "disabled" : ""}>▼</button>
          </div>
        </div>`;
      })
      .join("");

    const exceptions = (views.manual_exceptions || [])
      .map((view) => `<button class="chip on" data-exception="${esc(view)}">${esc(viewLabel(view))} ✕</button>`)
      .join("");
    const addable = PINNABLE.filter((view) => !(views.manual_exceptions || []).includes(view))
      .map((view) => `<button class="chip" data-exception-add="${esc(view)}">+ ${esc(viewLabel(view))}</button>`)
      .join("");

    return `
      <div class="card">
        <h2>${esc(t("panel.views.priority"))}</h2>
        <div class="hint">${esc(t("panel.views.priority.hint"))}</div>
        ${rows}
        <div class="actions"><button class="primary" data-save="views">${esc(t("common.save"))}</button></div>
        <div class="note">${esc(t("panel.views.note"))}</div>
      </div>

      ${this._cardSchedules()}

      <div class="card">
        <h2>${esc(t("panel.views.fallback"))}</h2>
        <label>${esc(t("panel.views.fallback.timeout"))}</label>
        <div class="inline">
          <input id="manual-timeout" value="${esc(fmtNum(views.manual_timeout_h ?? 4))}">
          <span class="unit">${esc(t("panel.views.fallback.hours"))}</span>
        </div>
        <div class="muted">${esc(t("panel.views.fallback.zero"))}</div>
        <label>${esc(t("panel.views.fallback.exceptions"))}</label>
        <div class="chips">${exceptions}${addable}</div>
        <label>${esc(t("panel.views.fallback.view"))}</label>
        <select id="fallback-view">
          ${PINNABLE.map(
            (view) => `<option value="${view}" ${views.fallback === view ? "selected" : ""}>${esc(viewLabel(view))}</option>`,
          ).join("")}
        </select>
        <div class="muted">${esc(t("panel.views.fallback.view.hint"))}</div>
        <div class="actions"><button class="primary" data-save="views">${esc(t("common.save"))}</button></div>
      </div>
    `;
  }

  _cardSchedules() {
    const schedule = this._draft.schedule || {};
    const helpers = Object.keys(this._hass.states || {})
      .filter((id) => id.startsWith("schedule."))
      .sort();
    const entries = Object.entries(schedule);

    const rows = entries
      .map(([view, entry]) => {
        const state = this._hass.states[entry.entity_id];
        const now = !state
          ? `<span class="muted">${esc(t("panel.views.schedules.missing"))}</span>`
          : state.state === "on"
            ? `<span style="color:var(--success-color,#43a047);font-weight:600">${esc(t("panel.views.schedules.running"))}</span>`
            : `<span class="muted">${esc(t("panel.views.schedules.off"))}</span>`;
        const options = helpers
          .map((id) => `<option value="${esc(id)}" ${entry.entity_id === id ? "selected" : ""}>${esc(id)}</option>`)
          .join("");
        return `<tr>
          <td>${esc(viewLabel(view))}</td>
          <td><select data-schedule-entity="${esc(view)}"><option value="">—</option>${options}</select></td>
          <td style="width:80px"><input data-schedule-rank="${esc(view)}" value="${esc(entry.rank ?? "")}"></td>
          <td>${now}</td>
          <td><button class="plain small" data-schedule-remove="${esc(view)}">✕</button></td>
        </tr>`;
      })
      .join("");

    const addable = PINNABLE.filter((view) => !(view in schedule));
    const add = addable.length
      ? `<div class="inline" style="margin-top:12px">
           <select id="schedule-add-view">${addable.map((v) => `<option value="${v}">${esc(viewLabel(v))}</option>`).join("")}</select>
           <button class="plain" id="schedule-add">${esc(t("panel.views.schedules.add"))}</button>
         </div>`
      : "";

    return `<div class="card">
      <h2>${esc(t("panel.views.schedules"))}</h2>
      <div class="hint">${esc(t("panel.views.schedules.hint"))}</div>
      ${
        entries.length
          ? `<table><thead><tr>
              <th>${esc(t("panel.views.schedules.view"))}</th>
              <th>${esc(t("panel.views.schedules.entity"))}</th>
              <th>${esc(t("panel.views.schedules.rank"))}</th>
              <th>${esc(t("panel.views.schedules.now"))}</th>
              <th></th></tr></thead><tbody>${rows}</tbody></table>`
          : `<div class="muted">${esc(t("panel.views.schedules.none"))}</div>`
      }
      ${add}
      <div class="actions">
        <button class="primary" data-save="schedule">${esc(t("common.save"))}</button>
        <button class="plain" id="open-helpers">${esc(t("panel.views.schedules.open"))}</button>
      </div>
      <div class="note">${esc(t("panel.views.schedules.overlap"))}</div>
    </div>`;
  }

  // --- page: calendar (FSD §8.1, kalenderkonzept.md Teil A) -----------------
  // Deliberately source-agnostic, exactly as the mockup draws it: a list of
  // entities with a person and a colour. What is behind one — M365 publish ICS,
  // Google, CalDAV, Local Calendar — never appears on this page, which is the
  // whole point of going through calendar.get_events. Moving Wolfgang's diary
  // from Microsoft to an IMAP provider later costs a line in this table and
  // nothing in the renderer.
  _pageCalendar() {
    const cal = this._draft.calendar || {};
    const sources = cal.sources || [];
    const admin = this.isAdmin;
    const lock = admin ? "" : "disabled";
    const probe = this._calendar || {};
    const counts = probe.counts || {};
    const failed = probe.failed || {};

    // What the last "Sync now" did. It stays on the card rather than fading
    // like the header notice: "the wall shows something else right now" is the
    // answer to "why did nothing change", and that question comes late.
    // Only an anniversary source can be written back to - an appointment has
    // no year in brackets and nothing to count [P42].
    const hasAnniversaries = sources.some((source) => source.kind === "birthdays");

    // Two different things, and the card shows both: what this installation
    // last *wrote* (from the status document, so it survives a reload and
    // covers the nightly run), and what the button just did.
    const state = ((this._status || {}).anniversaries) || null;
    const annivLast = state
      ? t("panel.calendar.anniv.state", {
          time: fmtDateTime(state.at) || "",
          written: fmtNum(state.written || 0),
          total: fmtNum(state.total || 0),
        })
      : t("panel.calendar.anniv.never");
    const anniv = this._anniv;
    const annivFailed = Object.entries((anniv || {}).failed || {});
    const annivNote = !anniv
      ? ""
      : `<div class="note${annivFailed.length ? " warn" : ""}">${esc(
          t("panel.calendar.anniv.done", {
            written: fmtNum(anniv.written || 0),
            total: fmtNum(anniv.sources.reduce((sum, one) => sum + (one.total || 0), 0)),
          }),
        )}</div>` +
        annivFailed
          .map(
            ([id, message]) =>
              `<div class="note bad">${esc(
                t("panel.calendar.anniv.failed", { entity: id, msg: message }),
              )}</div>`,
          )
          .join("");

    const sync = this._calendarSync;
    const syncNote = !sync
      ? ""
      : sync.on_wall
        ? `<div class="note">${esc(
            t("panel.calendar.sync.done", { time: fmtTime(sync.at) || "" }),
          )}</div>`
        : `<div class="note warn">${esc(
            t("panel.calendar.sync.other_view", { time: fmtTime(sync.at) || "" }),
          )}</div>`;

    // Every calendar entity Home Assistant knows about. Read out of hass
    // directly rather than through a command of our own — the panel already
    // holds the state machine, and this list is what it is for.
    const entities = Object.keys((this._hass || {}).states || {})
      .filter((id) => id.startsWith("calendar."))
      .sort();

    const rows = sources
      .map((source, index) => {
        const id = source.entity_id || "";
        // A configured entity that no longer exists must stay selectable, or
        // saving the page would quietly drop it.
        const options = (entities.includes(id) || !id ? entities : [id, ...entities])
          .map((candidate) => {
            const label = ((this._hass.states[candidate] || {}).attributes || {}).friendly_name;
            const missing = entities.includes(candidate) ? "" : " " + t("panel.calendar.gone");
            return '<option value="' + esc(candidate) + '"' + (candidate === id ? " selected" : "") +
              ">" + esc(candidate + (label ? " — " + label : "") + missing) + "</option>";
          })
          .join("");
        const kinds = CALENDAR_KINDS.map(
          (kind) =>
            '<option value="' + esc(kind) + '"' + (source.kind === kind ? " selected" : "") + ">" +
            esc(t("panel.calendar.kind." + kind)) + "</option>",
        ).join("");
        // A holiday belongs to nobody, so it wears no colour and stands in no
        // legend [P48]. The cell says so rather than going blank — an empty
        // box beside four filled ones reads as something that failed to load.
        const swatches =
          source.kind === CALENDAR_KIND_HOLIDAYS
            ? '<span class="muted">' + esc(t("panel.calendar.color.none")) + "</span>"
            : Object.entries(CALENDAR_COLORS)
                .map(
                  ([token, hex]) =>
                    '<button class="swatch ' + (source.color === token ? "on" : "") +
                    '" data-src-color="' + index + ":" + esc(token) + '" title="' +
                    esc(t("guests.color." + token)) + '" ' + lock + '><span style="background:' +
                    esc(hex) + '"></span></button>',
                )
                .join("");
        const answer = failed[id]
          ? '<span class="bad" title="' + esc(failed[id]) + '">' + esc(t("panel.calendar.failed")) + "</span>"
          : id in counts
            ? esc(String(counts[id]))
            : '<span class="muted">' + esc(probe.loading ? t("common.loading") : "—") + "</span>";
        return (
          "<tr>" +
          '<td><select data-src-entity="' + index + '" ' + lock + ">" + options + "</select></td>" +
          '<td><input data-src-person="' + index + '" value="' + esc(source.person || "") + '" ' + lock + "></td>" +
          '<td><select data-src-kind="' + index + '" ' + lock + ">" + kinds + "</select></td>" +
          '<td><div class="swatches">' + swatches + "</div></td>" +
          "<td>" + answer + "</td>" +
          '<td><button class="plain" data-src-remove="' + index + '" ' + lock + ">✕</button></td>" +
          "</tr>"
        );
      })
      .join("");

    return `
      ${admin ? "" : `<div class="card" style="grid-column: 1 / -1"><div class="note warn">${esc(t("error.no_admin"))}</div></div>`}

      <div class="card" style="grid-column: 1 / -1">
        <h2>${esc(t("panel.calendar.sources"))}</h2>
        <div class="hint">${esc(t("panel.calendar.sources.hint"))}</div>
        ${
          sources.length
            ? `<table><thead><tr>
                <th>${esc(t("panel.calendar.entity"))}</th>
                <th>${esc(t("panel.calendar.person"))}</th>
                <th>${esc(t("panel.calendar.kind"))}</th>
                <th>${esc(t("panel.calendar.color"))}</th>
                <th>${esc(t("panel.calendar.entries"))}</th>
                <th></th></tr></thead><tbody>${rows}</tbody></table>`
            : `<div class="muted">${esc(t("panel.calendar.sources.none"))}</div>`
        }
        ${
          probe.error
            ? `<div class="note bad">${esc(probe.error)}</div>`
            : ""
        }
        <div class="actions">
          <button class="plain" id="calendar-add" ${entities.length && admin ? "" : "disabled"}>${esc(
            t("panel.calendar.add"),
          )}</button>
          <button class="plain" id="calendar-probe" ${lock}>${esc(t("panel.calendar.recount"))}</button>
          <button class="plain" id="calendar-sync" ${
            lock || !sources.length || this._calendarSyncing ? "disabled" : ""
          }>${esc(
            this._calendarSyncing ? t("panel.calendar.sync.running") : t("panel.calendar.sync"),
          )}</button>
          <button class="primary" data-save="calendar" ${lock}>${esc(t("common.save"))}</button>
        </div>
        <div class="hint">${esc(t("panel.calendar.sync.hint"))}</div>
        ${syncNote}
        ${entities.length ? "" : `<div class="note warn">${esc(t("panel.calendar.no_entities"))}</div>`}
      </div>

      <div class="card">
        <h2>${esc(t("panel.calendar.anniv"))}</h2>
        <div class="hint">${esc(t("panel.calendar.anniv.hint"))}</div>
        <div class="kv">
          <div class="k">${esc(t("panel.calendar.anniv.last"))}</div>
          <div>${esc(annivLast)}</div>
        </div>
        <div class="row" style="margin-top:12px">
          <input type="checkbox" id="calendar-anniv-auto" ${
            cal.anniversary_writeback === false ? "" : "checked"
          } ${lock}>
          <label for="calendar-anniv-auto">${esc(t("panel.calendar.anniv.auto"))}</label>
        </div>
        <div class="muted">${esc(
          t("panel.calendar.anniv.auto.hint", {
            time: ((this._status || {}).anniversary_time) || "00:15",
          }),
        )}</div>
        <div class="actions">
          <button class="plain" id="calendar-anniv" ${
            hasAnniversaries && !this._annivRunning ? "" : "disabled"
          }>${esc(
            this._annivRunning
              ? t("panel.calendar.anniv.running")
              : t("panel.calendar.anniv.run"),
          )}</button>
          <button class="primary" data-save="calendar" ${lock}>${esc(t("common.save"))}</button>
        </div>
        ${hasAnniversaries ? "" : `<div class="muted">${esc(t("panel.calendar.anniv.none"))}</div>`}
        ${annivNote}
      </div>

      <div class="card">
        <h2>${esc(t("panel.calendar.window"))}</h2>
        <label>${esc(t("panel.calendar.days_events"))}</label>
        <div class="inline">
          <input id="calendar-days-events" value="${esc(fmtNum(cal.query_days_events ?? 30))}" ${lock}>
          <span class="unit">${esc(t("panel.calendar.days"))}</span>
        </div>
        <label>${esc(t("panel.calendar.days_birthdays"))}</label>
        <div class="inline">
          <input id="calendar-days-birthdays" value="${esc(fmtNum(cal.query_days_birthdays ?? 30))}" ${lock}>
          <span class="unit">${esc(t("panel.calendar.days"))}</span>
        </div>
        <div class="note">${esc(t("panel.calendar.window.hint"))}</div>
        <div class="actions"><button class="primary" data-save="calendar" ${lock}>${esc(t("common.save"))}</button></div>
      </div>

      <div class="card">
        <h2>${esc(t("panel.calendar.look"))}</h2>
        <label>${esc(t("panel.calendar.bar"))}</label>
        <div class="inline">
          <input id="calendar-bar-px" value="${esc(fmtNum(cal.color_bar_px ?? 6))}" ${lock}>
          <span class="unit">${esc(t("panel.guests.font.px"))}</span>
        </div>
        <div class="muted">${esc(t("panel.calendar.bar.hint"))}</div>
        <div class="row" style="margin-top:12px">
          <input type="checkbox" id="calendar-empty-days" ${cal.show_empty_days ? "checked" : ""} ${lock}>
          <label for="calendar-empty-days">${esc(t("panel.calendar.empty_days"))}</label>
        </div>
        <div class="muted">${esc(t("panel.calendar.empty_days.hint"))}</div>
        <div class="row" style="margin-top:12px">
          <input type="checkbox" id="calendar-past-today" ${cal.show_past_today ? "checked" : ""} ${lock}>
          <label for="calendar-past-today">${esc(t("panel.calendar.past_today"))}</label>
        </div>
        <div class="muted">${esc(t("panel.calendar.past_today.hint"))}</div>
        <div class="actions"><button class="primary" data-save="calendar" ${lock}>${esc(t("common.save"))}</button></div>
      </div>
    `;
  }

  // --- page: recipes --------------------------------------------------------
  // What is on the wall and what could be. The Paprika account lives under
  // Settings; **the state of the cache stays here** — "are the new recipes here
  // yet?" is a question somebody asks while cooking, not while configuring, and
  // C11 asked for it in as many words.
  _pageRecipes() {
    const cache = ((this._status || {}).recipes) || {};
    // Nothing on this page is locked [2026-08-31, Wolfgang]. Picking the
    // recipes and pressing "sync now" are both household business: the first is
    // a decision about tonight, the second answers "are the new recipes here
    // yet?" — the question C11 built this page around. What stays
    // administrator-only is the Paprika account, and that lives under Settings.

    const synced = fmtDateTime(cache.synced_at);
    const cacheLine = cache.count
      ? t("panel.recipes.sync.count", { count: fmtNum(cache.count) })
      : t("panel.recipes.search.empty_cache");

    let cacheNote = "";
    if (!cache.configured || cache.error === "no_credentials")
      cacheNote = `<div class="note warn">${esc(t("panel.recipes.error.no_credentials"))}</div>
                   <div class="actions"><button class="plain" id="to-settings">${esc(
                     t("panel.recipes.account.open"),
                   )}</button></div>`;
    else if (cache.error)
      cacheNote = `<div class="note bad">${esc(t("panel.recipes.error.sync", { msg: cache.error }))}</div>`;
    else if (cache.pending)
      cacheNote = `<div class="note warn">${esc(t("panel.recipes.sync.pending", { count: fmtNum(cache.pending) }))}</div>`;

    return `
      <div class="card">
        <h2>${esc(t("panel.recipes.cache"))}</h2>
        <div class="hint">${esc(t("panel.recipes.cache.hint"))}</div>
        <div class="kv">
          <div class="k">${esc(t("panel.recipes.sync.last"))}</div>
          <div>${esc(synced || t("panel.recipes.sync.never"))}</div>
          <div class="k">${esc(t("panel.tab.recipes"))}</div>
          <div>${esc(cacheLine)}</div>
        </div>
        <div class="actions">
          <button class="plain" id="sync-recipes" ${this._syncing ? "disabled" : ""}>${esc(
            this._syncing ? t("panel.recipes.sync.running") : t("panel.recipes.sync"),
          )}</button>
        </div>
        ${cacheNote}
      </div>

      ${this._cardSlots()}

      <div class="card" style="grid-column: 1 / -1">
        <h2>${esc(t("panel.recipes.search"))}</h2>
        <div class="hint">${esc(t("panel.recipes.search.hint"))}</div>
        <input id="recipe-search" value="${esc(this._query)}"
               placeholder="${esc(t("panel.recipes.search.placeholder"))}">
        <div id="hits">${this._hitRows()}</div>
      </div>
    `;
  }

  _cardSlots() {
    // That open question is decided [2026-08-31, Wolfgang]: yes, the household
    // picks tonight's recipe the way it switches the view. It did need its own
    // narrow command, and it has one — epaperengine/recipes/select, which sends
    // the selection and the portion counts and nothing else.
    const selection = ((this._draft.recipes || {}).selection || []).slice(0, RECIPE_SLOTS);
    // Ordered the way the columns stand on the wall, not the way the cache
    // answered — the slot number is the column number.
    const byUid = new Map(this._picked.map((recipe) => [recipe.uid, recipe]));

    const rows = selection
      .map((uid, index) => {
        const recipe = byUid.get(uid);
        const name = recipe ? recipe.name : uid;
        const known = recipe ? this._forecast.get(uid) : null;
        // The number the recipe was written for, and the number it is being
        // cooked for. An empty `servings` in Paprika means there is no base to
        // scale from, so the field is not offered at all.
        const base = recipe ? String(recipe.servings || "").trim() : "";
        const scalable = /^[\d.,]+$/.test(base);
        const target = ((this._draft.recipes || {}).servings || {})[uid];
        return `<div class="sortrow">
          <div class="grow">
            <div class="name">${esc(name)}</div>
            <div class="why">${esc(t("panel.recipes.slot", { n: index + 1 }))}${
              known
                ? ` · ${esc(
                    fitsAt(known.fits, selection.length)
                      ? t("panel.recipes.fit.yes")
                      : t("panel.recipes.fit.no"),
                  )} · ${esc(t("panel.recipes.chars", { count: fmtNum(known.chars || 0) }))}`
                : ""
            }</div>
          ${
            known && !fitsAt(known.fits, selection.length)
              ? `<span style="color:var(--error-color,#db4437);font-weight:600">✗</span>`
              : ""
          }
          </div>
          ${
            scalable
              ? `<div class="servings">
                   <span class="muted">${esc(t("panel.recipes.servings.base"))} ${esc(base)}</span>
                   <label class="muted" for="serve-${esc(uid)}">${esc(t("panel.recipes.servings.target"))}</label>
                   <input id="serve-${esc(uid)}" data-servings="${esc(uid)}" inputmode="decimal"
                          value="${esc(target == null ? "" : fmtNum(target))}" placeholder="${esc(base)}">
                 </div>`
              : `<span class="muted">${esc(t("panel.recipes.servings.none"))}</span>`
          }
          <div class="rank">
            <button class="plain small" data-slot-move="up" data-slot="${index}" title="${esc(t("panel.views.up"))}" ${index === 0 ? "disabled" : ""}>▲</button>
            <button class="plain small" data-slot-move="down" data-slot="${index}" title="${esc(t("panel.views.down"))}" ${index === selection.length - 1 ? "disabled" : ""}>▼</button>
          </div>
          <button class="plain small" data-unpick="${esc(uid)}">✕</button>
        </div>`;
      })
      .join("");

    return `<div class="card">
      <h2>${esc(t("panel.recipes.selection"))}</h2>
      <div class="hint">${esc(t("panel.recipes.selection.hint"))}</div>
      ${rows || `<div class="muted">${esc(t("panel.recipes.selection.empty"))}</div>`}
      ${rows ? `<div class="note">${esc(t("panel.recipes.servings.hint"))}</div>` : ""}
    </div>`;
  }

  _hitRows() {
    const found = this._recipes;
    if (!found) return `<div class="muted">${esc(t("common.loading"))}</div>`;
    if (found.error) return `<div class="note bad">${esc(found.error)}</div>`;
    const hits = found.hits || [];
    if (!hits.length) {
      return `<div class="muted">${esc(
        found.total ? t("panel.recipes.search.none") : t("panel.recipes.search.empty_cache"),
      )}</div>`;
    }
    const selection = (this._draft.recipes || {}).selection || [];
    const full = selection.length >= RECIPE_SLOTS;

    const rows = hits
      .map((hit) => {
        const picked = selection.includes(hit.uid);
        return `<tr>
          <td>${esc(hit.name)}</td>
          <td class="muted">${esc((hit.categories || []).join(" · "))}</td>
          <td class="muted" style="white-space:nowrap">${esc(
            t("panel.recipes.chars", { count: fmtNum(hit.chars || 0) }),
          )}</td>
          <td style="white-space:nowrap" title="${esc(fitTitle(hit.fits))}">${fitTriple(hit.fits)}</td>
          <td style="width:1%">
            ${
              picked
                ? `<button class="plain small" data-unpick="${esc(hit.uid)}">✕</button>`
                : `<button class="plain small" data-pick="${esc(hit.uid)}" ${full ? "disabled" : ""}>${esc(t("panel.recipes.add"))}</button>`
            }
          </td>
        </tr>`;
      })
      .join("");

    const more =
      found.total > hits.length
        ? `<div class="muted" style="margin-top:8px">${esc(
            t("panel.recipes.search.more", { count: fmtNum(found.total - hits.length) }),
          )}</div>`
        : "";
    const fullNote = full ? `<div class="note">${esc(t("panel.recipes.full"))}</div>` : "";
    return `<table><thead><tr>
        <th>${esc(t("panel.tab.recipes"))}</th>
        <th></th>
        <th></th>
        <th title="${esc(t("panel.recipes.fit.slots.hint"))}">${esc(t("panel.recipes.fit.slots"))}</th>
        <th></th>
      </tr></thead><tbody>${rows}</tbody></table>${more}${fullNote}`;
  }

  // --- page: photos ---------------------------------------------------------
  // The rotation and what is in the cache. The folders live under Settings —
  // they are typed once, when the NAS is mounted.
  _pagePhotos() {
    const photos = this._draft.photos || {};
    const cache = this._photos;

    const thumbs =
      cache && cache.photos && cache.photos.length
        ? `<div class="thumbs">${cache.photos
            .slice(0, 60)
            .map(
              (photo) => `<div class="thumb">
                 <img loading="lazy" src="${esc(photo.url || "")}" alt="${esc(photo.name)}">
                 <div class="cap" title="${esc(photo.name)}">${esc(photo.name)}</div>
               </div>`,
            )
            .join("")}</div>`
        : `<div class="muted">${esc((cache && cache.error) || t("panel.photos.cache.none"))}</div>`;

    return `
      <div class="card">
        <h2>${esc(t("panel.photos.rotation"))}</h2>
        <label>${esc(t("panel.photos.rotation.interval"))}</label>
        <div class="inline">
          <input id="rotation" value="${esc(fmtNum(photos.rotation_interval_min ?? 60))}">
          <span class="unit">${esc(t("panel.photos.rotation.minutes"))}</span>
        </div>
        <div class="muted">${esc(t("panel.photos.rotation.hint"))}</div>
        <div class="actions"><button class="primary" data-save="photos">${esc(t("common.save"))}</button></div>
        <div class="note warn">${esc(t("panel.photos.budget.hint"))}</div>
      </div>

      <div class="card" style="grid-column: 1 / -1">
        <h2>${esc(t("panel.photos.cache"))}</h2>
        <div class="hint">${esc(
          cache ? t("panel.photos.cache.count", { count: fmtNum(cache.total || 0) }) : t("common.loading"),
        )}</div>
        ${thumbs}
        <div class="actions"><button class="plain" id="reload-photos">${esc(t("panel.photos.cache.reload"))}</button></div>
      </div>
    `;
  }

  // --- page: guests ---------------------------------------------------------
  // The mockup (06-panel-gaeste) in four cards: the switch, the text, the type,
  // the picture. The switch is **state** and commits on the click; everything
  // else is configuration and waits for Save — except picking a picture, which
  // is a decision about tonight (see ``_pickBackground``).
  _pageGuests() {
    const guests = this._draft.guests || {};
    const status = this._status || {};
    const active = !!status.guests_active;
    const since = fmtDateTime(status.guests_since);
    const admin = this.isAdmin;
    const lock = admin ? "" : "disabled";
    const cache = this._backgrounds;

    // One builder for both pickers — the fill and the seam offer the same six.
    const swatchRow = (attribute, chosen) =>
      Object.entries(GUEST_COLORS)
        .map(
          ([id, hex]) =>
            `<button class="swatch ${chosen === id ? "on" : ""}" ${attribute}="${esc(id)}"
               title="${esc(t(`guests.color.${id}`))}" ${lock}
             ><span style="background:${esc(hex)}"></span>${esc(t(`guests.color.${id}`))}</button>`,
        )
        .join("");
    const swatches = swatchRow("data-color", guests.color);
    const outlineSwatches = swatchRow("data-outline-color", guests.outline_color);

    const fontOptions = GUEST_FONTS.map(
      (id) =>
        `<option value="${esc(id)}" ${guests.font === id ? "selected" : ""}>${esc(t(`guests.font.${id}`))}</option>`,
    ).join("");

    const blank = `<div class="thumb pick ${guests.background ? "" : "on"}" data-background="">
        <div class="blank">${esc(t("panel.guests.background.none"))}</div>
        <div class="cap">&nbsp;</div>
      </div>`;

    let tiles = "";
    if (!admin) tiles = `<div class="muted">${esc(t("error.no_admin"))}</div>`;
    else if (cache && cache.loading) tiles = `<div class="muted">${esc(t("common.loading"))}</div>`;
    else if (cache && cache.error)
      tiles = `<div class="note bad">${esc(t("panel.guests.background.error", { msg: cache.error }))}</div>`;
    else if (cache)
      tiles = `<div class="thumbs">${blank}${(cache.backgrounds || [])
        .map(
          (item) => `<div class="thumb pick ${guests.background === item.digest ? "on" : ""}" data-background="${esc(item.digest)}">
             <img loading="lazy" src="${esc(item.url || "")}" alt="${esc(item.name)}">
             <div class="cap" title="${esc(item.name)}">${esc(item.name)}</div>
           </div>`,
        )
        .join("")}</div>`;
    if (admin && cache && !cache.error && !cache.loading && !(cache.backgrounds || []).length)
      tiles += `<div class="muted">${esc(t("panel.guests.background.empty"))}</div>`;

    return `
      ${admin ? "" : `<div class="card" style="grid-column: 1 / -1"><div class="note warn">${esc(t("error.no_admin"))}</div></div>`}

      <div class="card">
        <h2>${esc(t("panel.guests.mode"))}</h2>
        <div class="row">
          <button class="${active ? "primary" : "plain"}" id="toggle-guests">${esc(
            active ? t("panel.guests.mode.turn_off") : t("panel.guests.mode.turn_on"),
          )}</button>
          <span class="${active ? "" : "muted"}">${esc(
            active
              ? since
                ? t("panel.guests.mode.on", { time: since })
                : t("panel.guests.mode.on.unknown")
              : t("panel.guests.mode.off"),
          )}</span>
        </div>
        <div class="muted">${esc(t("panel.guests.mode.hint"))}</div>
        <div class="muted">${esc(t("panel.guests.mode.priority"))}</div>
      </div>

      <div class="card">
        <h2>${esc(t("panel.guests.text"))}</h2>
        <label>${esc(t("panel.guests.name"))}</label>
        <input id="guest-name" value="${esc(guests.name || "")}" ${lock}>
        <label>${esc(t("panel.guests.greeting"))}</label>
        <input id="guest-greeting" value="${esc(guests.greeting || "")}" ${lock}>
        <div class="actions"><button class="primary" data-save="guests" ${lock}>${esc(t("common.save"))}</button></div>
      </div>

      <div class="card">
        <h2>${esc(t("panel.guests.font"))}</h2>
        <label>${esc(t("panel.guests.font.face"))}</label>
        <select id="guest-font" ${lock}>${fontOptions}</select>
        <label>${esc(t("panel.guests.font.name_px"))}</label>
        <div class="inline">
          <input id="guest-name-px" value="${esc(fmtNum(guests.name_px ?? 180))}" ${lock}>
          <span class="unit">${esc(t("panel.guests.font.px"))}</span>
        </div>
        <label>${esc(t("panel.guests.font.greeting_px"))}</label>
        <div class="inline">
          <input id="guest-greeting-px" value="${esc(fmtNum(guests.greeting_px ?? 72))}" ${lock}>
          <span class="unit">${esc(t("panel.guests.font.px"))}</span>
        </div>
        <div class="muted">${esc(t("panel.guests.font.hint"))}</div>
        <label>${esc(t("panel.guests.color"))}</label>
        <div class="swatches">${swatches}</div>
        <div class="muted">${esc(t("panel.guests.color.hint"))}</div>
        <label>${esc(t("panel.guests.angle"))}</label>
        <div class="inline">
          <input id="guest-angle" value="${esc(fmtNum(guests.angle ?? 0))}" ${lock}>
          <span class="unit">${esc(t("panel.guests.angle.degrees"))}</span>
        </div>
        <div class="muted">${esc(t("panel.guests.angle.hint"))}</div>
        <div class="actions"><button class="primary" data-save="guests" ${lock}>${esc(t("common.save"))}</button></div>
      </div>

      <div class="card">
        <h2>${esc(t("panel.guests.outline"))}</h2>
        <div class="hint">${esc(t("panel.guests.outline.hint"))}</div>
        <div class="row">
          <input type="checkbox" id="guest-outline" ${guests.outline ? "checked" : ""} ${lock}>
          <label for="guest-outline">${esc(t("panel.guests.outline.on"))}</label>
        </div>
        <label>${esc(t("panel.guests.outline.width"))}</label>
        <div class="inline">
          <input id="guest-outline-px" value="${esc(fmtNum(guests.outline_px ?? 8))}" ${lock}>
          <span class="unit">${esc(t("panel.guests.font.px"))}</span>
        </div>
        <div class="muted">${esc(t("panel.guests.outline.width.hint"))}</div>
        <label>${esc(t("panel.guests.outline.color"))}</label>
        <div class="swatches">${outlineSwatches}</div>
        <div class="actions"><button class="primary" data-save="guests" ${lock}>${esc(t("common.save"))}</button></div>
      </div>

      <div class="card" style="grid-column: 1 / -1">
        <h2>${esc(t("panel.guests.background"))}</h2>
        <div class="hint">${esc(
          cache && cache.folder ? t("panel.guests.background.folder", { path: cache.folder }) : t("common.loading"),
        )}</div>
        ${tiles}
        <div class="actions">
          <button class="plain" id="reload-backgrounds" ${lock}>${esc(t("panel.guests.background.reload"))}</button>
        </div>
        <div class="note warn">${esc(t("panel.guests.check.hint"))}</div>
      </div>
    `;
  }

  // --- page: settings -------------------------------------------------------
  // Everything an administrator sets once and then forgets: the display, the
  // Paprika account, the image paths [Festlegung 2026-08-22]. It is also the
  // one page that is administrator-only as a whole, which is what makes the
  // permission rule sayable in a sentence.
  _pageSettings() {
    const display = this._draft.display || {};
    const probed = (this._status && this._status.display) || {};
    const battery = probed.battery || {};
    const probe = this._probe;

    let probeNote = "";
    if (probe && probe.pending) probeNote = `<div class="note">${esc(t("common.loading"))}</div>`;
    else if (probe && probe.reachable)
      probeNote = `<div class="note">${esc(t("panel.display.test.ok"))}</div>`;
    else if (probe)
      probeNote = `<div class="note bad">${esc(t("panel.display.test.failed", { msg: probe.error || t("error.unknown") }))}</div>`;

    const admin = this.isAdmin;
    const lock = admin ? "" : "disabled";

    const recipes = this._draft.recipes || {};
    const login = recipes.paprika_login || {};
    // Redacted for everybody but an administrator (websocket_api._visible_config):
    // a string is the real password, `true` only says one is stored.
    const password = typeof login.password === "string" ? login.password : "";
    const hasPassword = !!login.password;
    const media = this._draft.media || {};
    const photos = this._draft.photos || {};

    return `
      ${admin ? "" : `<div class="card" style="grid-column: 1 / -1"><div class="note warn">${esc(t("error.no_admin"))}</div></div>`}

      <div class="card">
        <h2>${esc(t("panel.recipes.account"))}</h2>
        <div class="hint">${esc(t("panel.recipes.account.hint"))}</div>
        <label>${esc(t("panel.recipes.username"))}</label>
        <input id="paprika-user" value="${esc(login.username || "")}" ${lock}>
        <label>${esc(t("panel.recipes.password"))}</label>
        <input id="paprika-password" type="password" value="${esc(password)}" ${lock}>
        ${!admin && hasPassword ? `<div class="muted">${esc(t("panel.recipes.password.set"))}</div>` : ""}
        <label>${esc(t("panel.recipes.interval"))}</label>
        <div class="inline">
          <input id="sync-interval" value="${esc(fmtNum(recipes.sync_interval_h ?? 24))}" ${lock}>
          <span class="unit">${esc(t("panel.recipes.interval.hours"))}</span>
        </div>
        <div class="muted">${esc(t("panel.recipes.interval.hint"))}</div>
        <div class="actions"><button class="primary" data-save="recipes" ${lock}>${esc(t("common.save"))}</button></div>
      </div>

      <div class="card">
        <h2>${esc(t("panel.photos.source"))}</h2>
        <div class="hint">${esc(t("panel.settings.paths.hint"))}</div>
        <label>${esc(t("panel.photos.root"))}</label>
        <input id="media-root" value="${esc(media.root || "")}" placeholder="/media/epaperengine" ${lock}>
        <div class="muted">${esc(t("panel.photos.root.hint"))}</div>
        <label>${esc(t("panel.photos.source.folder"))}</label>
        <input id="photo-folder" value="${esc(photos.source_folder || "")}" ${lock}>
        <div class="muted">${esc(t("panel.photos.source.hint"))}</div>
        <div class="actions"><button class="primary" data-save="photos,media" ${lock}>${esc(t("common.save"))}</button></div>
      </div>

      <div class="card">
        <h2>${esc(t("panel.display.connection"))}</h2>
        <label>${esc(t("panel.display.host"))}</label>
        <input id="display-host" value="${esc(display.host || "")}" ${lock}>
        <label>${esc(t("panel.display.pin"))}</label>
        <input id="display-pin" type="password" value="${esc(display.mdc_pin || "")}" ${lock}>
        <label>${esc(t("panel.display.mac"))}</label>
        <input id="display-mac" value="${esc(display.mac || "")}" ${lock}>
        <div class="actions">
          <button class="primary" data-save="display" ${lock}>${esc(t("common.save"))}</button>
          <button class="plain" id="test-display" ${lock}>${esc(t("panel.display.test"))}</button>
        </div>
        <div class="muted">${esc(t("panel.display.test.hint"))}</div>
        ${probeNote}
      </div>

      <div class="card">
        <h2>${esc(t("panel.display.renderer"))}</h2>
        <label>${esc(t("panel.display.renderer.url"))}</label>
        <input id="renderer-url" value="${esc(display.renderer_url || "")}" placeholder="http://homeassistant.local:8099" ${lock}>
        <div class="muted">${esc(t("panel.display.renderer.hint"))}</div>
        <div class="actions"><button class="primary" data-save="display" ${lock}>${esc(t("common.save"))}</button></div>
      </div>

      <div class="card">
        <h2>${esc(t("panel.display.safety"))}</h2>
        <div class="note warn">${esc(t("panel.display.safety.hint"))}</div>
        <div class="row" style="margin-top:12px">
          <input type="checkbox" id="display-push" ${display.push_enabled === false ? "" : "checked"} ${lock}>
          <label for="display-push">${esc(t("panel.display.push"))}</label>
        </div>
        <div class="muted">${esc(t("panel.display.push.hint"))}</div>
        <div class="actions"><button class="primary" data-save="display" ${lock}>${esc(t("common.save"))}</button></div>
      </div>

      <div class="card">
        <h2>${esc(t("panel.display.device"))}</h2>
        <div class="hint">${esc(t("panel.display.device.hint"))}</div>
        <div class="kv">
          <div class="k">${esc(t("panel.display.device.name"))}</div><div>${esc(probed.device_name || t("common.unknown"))}</div>
          <div class="k">${esc(t("panel.display.device.firmware"))}</div><div>${esc(probed.software_version || t("common.unknown"))}</div>
          <div class="k">${esc(t("panel.display.device.serial"))}</div><div>${esc(probed.serial_number || t("common.unknown"))}</div>
          <div class="k">${esc(t("panel.display.device.power"))}</div><div>${esc(probed.power_state || t("common.unknown"))}</div>
          <div class="k">${esc(t("panel.display.device.battery"))}</div>
          <div>${
            battery.batteryPercent == null
              ? esc(t("common.unknown"))
              : esc(`${fmtNum(battery.batteryPercent)} %${battery.pluggedIn ? ` · ${t("panel.display.device.plugged")}` : ""}`)
          }</div>
        </div>
        ${probed.at ? `<div class="muted" style="margin-top:10px">${esc(t("panel.display.checked", { time: probed.at }))}</div>` : ""}
        ${probed.error ? `<div class="note bad">${esc(probed.error)}</div>` : ""}
      </div>
    `;
  }

  // --- wiring ---------------------------------------------------------------
  _wire() {
    const root = this.shadowRoot;
    const on = (selector, handler) => {
      const node = root.querySelector(selector);
      if (node) node.onclick = handler;
    };

    root.querySelectorAll("nav a").forEach((link) => {
      link.onclick = () => this._go(link.dataset.tab);
    });
    on("#to-dashboard", () => this._toDashboard());
    on("#do-render", () => this._render_now(false));
    on("#do-push", () => this._render_now(true));

    // --- overview
    root.querySelectorAll("[data-view]").forEach((chip) => {
      chip.onclick = () => this._setView(chip.dataset.view || null);
    });
    on("#to-auto", () => this._setView(null));

    // --- views
    root.querySelectorAll("[data-move]").forEach((button) => {
      button.onclick = () => {
        const list = (this._draft.views.priority || []).filter((c) => CANDIDATES.includes(c));
        const index = Number(button.dataset.index);
        const to = button.dataset.move === "up" ? index - 1 : index + 1;
        if (to < 0 || to >= list.length) return;
        [list[index], list[to]] = [list[to], list[index]];
        this._draft.views.priority = list;
        this._render();
      };
    });
    root.querySelectorAll("[data-exception]").forEach((chip) => {
      chip.onclick = () => {
        this._draft.views.manual_exceptions = (this._draft.views.manual_exceptions || []).filter(
          (view) => view !== chip.dataset.exception,
        );
        this._render();
      };
    });
    root.querySelectorAll("[data-exception-add]").forEach((chip) => {
      chip.onclick = () => {
        this._draft.views.manual_exceptions = [
          ...(this._draft.views.manual_exceptions || []),
          chip.dataset.exceptionAdd,
        ];
        this._render();
      };
    });
    root.querySelectorAll("[data-schedule-entity]").forEach((select) => {
      select.onchange = () => {
        this._draft.schedule[select.dataset.scheduleEntity].entity_id = select.value || null;
      };
    });
    root.querySelectorAll("[data-schedule-rank]").forEach((input) => {
      input.onchange = () => {
        const value = parseNum(input.value);
        this._draft.schedule[input.dataset.scheduleRank].rank = isFinite(value) ? value : null;
      };
    });
    root.querySelectorAll("[data-schedule-remove]").forEach((button) => {
      button.onclick = () => {
        delete this._draft.schedule[button.dataset.scheduleRemove];
        this._render();
      };
    });
    on("#schedule-add", () => {
      const view = root.querySelector("#schedule-add-view").value;
      const used = Object.values(this._draft.schedule || {})
        .map((entry) => Number(entry.rank))
        .filter((rank) => isFinite(rank));
      this._draft.schedule = {
        ...(this._draft.schedule || {}),
        [view]: { entity_id: null, rank: used.length ? Math.max(...used) + 1 : 1 },
      };
      this._render();
    });
    on("#open-helpers", () => {
      history.pushState(null, "", "/config/helpers");
      window.dispatchEvent(new CustomEvent("location-changed", { bubbles: true, composed: true }));
    });

    // --- recipes
    const search = root.querySelector("#recipe-search");
    if (search) {
      search.oninput = () => this._searchLater(search.value);
      // A repaint of the hit list moves focus nowhere, but a full re-render
      // does — put the caret back where the typing was.
      if (this._query && document.activeElement !== search) {
        const end = search.value.length;
        search.setSelectionRange(end, end);
      }
    }
    on("#sync-recipes", () => this._syncRecipes());
    on("#to-settings", () => this._go("settings"));
    this._wireHits();
    root.querySelectorAll("[data-servings]").forEach((input) => {
      input.onchange = () => {
        const uid = input.dataset.servings;
        const value = parseNum(input.value);
        const servings = { ...((this._draft.recipes || {}).servings || {}) };
        // An empty field means "as written" — the key goes away rather than
        // standing there as a number that happens to match.
        if (isFinite(value) && value > 0) servings[uid] = value;
        else delete servings[uid];
        this._draft.recipes.servings = servings;
        this._saveSelection();
      };
    });
    root.querySelectorAll("[data-slot-move]").forEach((button) => {
      button.onclick = () =>
        this._moveSlot(Number(button.dataset.slot), button.dataset.slotMove === "up" ? -1 : 1);
    });

    // --- calendar
    on("#calendar-add", () => {
      this._collect();
      const used = new Set((this._draft.calendar.sources || []).map((source) => source.entity_id));
      const free = Object.keys((this._hass || {}).states || {})
        .filter((id) => id.startsWith("calendar.") && !used.has(id))
        .sort();
      // The next unused colour, so two calendars never arrive sharing one bar.
      const taken = new Set((this._draft.calendar.sources || []).map((source) => source.color));
      const palette = Object.keys(CALENDAR_COLORS);
      this._draft.calendar.sources = [
        ...(this._draft.calendar.sources || []),
        {
          entity_id: free[0] || "",
          person: "",
          color: palette.find((token) => !taken.has(token)) || palette[0],
          kind: "events",
        },
      ];
      this._render();
    });
    on("#calendar-probe", () => {
      this._collect();
      this._calendar = { loading: true };
      this._render();
      this._probeCalendar();
    });
    on("#calendar-anniv", () => {
      this._collect();
      this._writeAnniversaries();
    });
    on("#calendar-sync", () => {
      // Collect first: the press blurs whatever field was being typed in, and
      // the repaint that follows would otherwise throw the draft away.
      this._collect();
      this._syncCalendar();
    });
    root.querySelectorAll("[data-src-remove]").forEach((button) => {
      button.onclick = () => {
        this._collect();
        const index = Number(button.dataset.srcRemove);
        this._draft.calendar.sources = (this._draft.calendar.sources || []).filter(
          (_, position) => position !== index,
        );
        this._render();
      };
    });
    root.querySelectorAll("[data-src-kind]").forEach((select) => {
      // The kind decides whether the row has a colour cell at all, so the card
      // has to be repainted when it changes. Collect first, exactly as the
      // swatch and the remove button do: the repaint rebuilds every field from
      // the draft, and a half-typed name would be gone.
      select.onchange = () => {
        this._collect();
        this._render();
      };
    });
    root.querySelectorAll("[data-src-color]").forEach((button) => {
      button.onclick = () => {
        // Read the page first — the swatch repaints the card, and a half-typed
        // person would be rebuilt from the draft and lost.
        this._collect();
        const [index, token] = button.dataset.srcColor.split(":");
        const sources = this._draft.calendar.sources || [];
        if (sources[Number(index)]) sources[Number(index)].color = token;
        this._render();
      };
    });

    // --- photos
    on("#reload-photos", () => this._loadPhotos());

    // --- guests
    on("#toggle-guests", () => this._setGuests(!(this._status || {}).guests_active));
    on("#reload-backgrounds", () => {
      this._backgrounds = { loading: true, backgrounds: [] };
      this._render();
      this._loadBackgrounds();
    });
    const pickColour = (selector, key) =>
      root.querySelectorAll(selector).forEach((button) => {
        button.onclick = () => {
          // Read the rest of the page first: the swatch repaints the card, and
          // a half-typed name would be rebuilt from the draft and lost.
          this._collect();
          this._draft.guests[key] = button.dataset[key === "color" ? "color" : "outlineColor"];
          this._render();
        };
      });
    pickColour("[data-color]", "color");
    pickColour("[data-outline-color]", "outline_color");
    root.querySelectorAll("[data-background]").forEach((tile) => {
      if (!this.isAdmin) return;
      tile.onclick = () => this._pickBackground(tile.dataset.background);
    });

    // --- save buttons: read the inputs of the page, then commit the sections
    root.querySelectorAll("[data-save]").forEach((button) => {
      button.onclick = () => {
        this._collect();
        this._save(button.dataset.save.split(","));
      };
    });
    on("#test-display", () => this._testDisplay());
  }

  /** Click handlers of the hit list and the slots — rebound on a partial repaint. */
  _wireHits() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-pick]").forEach((button) => {
      button.onclick = () => this._pick(button.dataset.pick);
    });
    root.querySelectorAll("[data-unpick]").forEach((button) => {
      button.onclick = () => this._unpick(button.dataset.unpick);
    });
  }

  /**
   * Pull the free-text fields of the current page into the draft.
   *
   * Read on save rather than on every keystroke: a re-render on each character
   * would fight the cursor, and the 15-second status poll re-renders anyway.
   */
  _collect() {
    const root = this.shadowRoot;
    const value = (selector) => {
      const node = root.querySelector(selector);
      return node ? node.value.trim() : null;
    };
    const number = (selector, fallback) => {
      const parsed = parseNum(value(selector));
      return isFinite(parsed) ? parsed : fallback;
    };

    if (this._tab === "views") {
      this._draft.views.manual_timeout_h = number("#manual-timeout", this._draft.views.manual_timeout_h);
      const fallback = value("#fallback-view");
      if (fallback) this._draft.views.fallback = fallback;
    }
    if (this._tab === "calendar") {
      // The rows are rebuilt from the DOM rather than patched in place: the
      // index in the data attribute is the row's position, and reading the
      // whole table at once is the only way that survives a removal.
      const rows = [...root.querySelectorAll("[data-src-entity]")];
      this._draft.calendar.sources = rows.map((select, index) => {
        const person = root.querySelector('[data-src-person="' + index + '"]');
        const kind = root.querySelector('[data-src-kind="' + index + '"]');
        const previous = (this._draft.calendar.sources || [])[index] || {};
        return {
          entity_id: select.value || "",
          person: person ? person.value.trim() : "",
          kind: kind ? kind.value : "events",
          color: previous.color || "blue",
        };
      });
      this._draft.calendar.query_days_events = number(
        "#calendar-days-events",
        this._draft.calendar.query_days_events,
      );
      this._draft.calendar.query_days_birthdays = number(
        "#calendar-days-birthdays",
        this._draft.calendar.query_days_birthdays,
      );
      this._draft.calendar.color_bar_px = number("#calendar-bar-px", this._draft.calendar.color_bar_px);
      const empty = root.querySelector("#calendar-empty-days");
      const past = root.querySelector("#calendar-past-today");
      if (empty) this._draft.calendar.show_empty_days = !!empty.checked;
      if (past) this._draft.calendar.show_past_today = !!past.checked;
      const auto = root.querySelector("#calendar-anniv-auto");
      if (auto) this._draft.calendar.anniversary_writeback = !!auto.checked;
    }
    if (this._tab === "photos") {
      this._draft.photos.rotation_interval_min = number(
        "#rotation",
        this._draft.photos.rotation_interval_min,
      );
    }
    if (this._tab === "guests") {
      const font = root.querySelector("#guest-font");
      this._draft.guests.name = value("#guest-name") || null;
      this._draft.guests.greeting = value("#guest-greeting") || null;
      if (font) this._draft.guests.font = font.value;
      // Zero is a real angle, so the fallback has to be the draft value and the
      // guard has to be isFinite — ``|| 0`` would be right by accident here and
      // wrong the moment somebody clears the field.
      this._draft.guests.angle = number("#guest-angle", this._draft.guests.angle ?? 0);
      const outline = root.querySelector("#guest-outline");
      // A checkbox is read from ``checked``; ``value`` on one is the literal
      // string "on" whether it is ticked or not, which would store a seam that
      // could never be switched off again.
      if (outline) this._draft.guests.outline = !!outline.checked;
      this._draft.guests.outline_px = number("#guest-outline-px", this._draft.guests.outline_px);
      this._draft.guests.name_px = number("#guest-name-px", this._draft.guests.name_px);
      this._draft.guests.greeting_px = number(
        "#guest-greeting-px",
        this._draft.guests.greeting_px,
      );
    }
    if (this._tab === "settings") {
      const username = value("#paprika-user");
      const password = value("#paprika-password");
      // Written as one object rather than two keys: the section merge in
      // ``async_set_config`` replaces whole keys, so a half-written login would
      // leave the old password standing next to the new address.
      this._draft.recipes.paprika_login =
        username || password ? { username: username || null, password: password || null } : null;
      this._draft.recipes.sync_interval_h = number(
        "#sync-interval",
        this._draft.recipes.sync_interval_h,
      );
      this._draft.media.root = value("#media-root") || null;
      this._draft.photos.source_folder = value("#photo-folder") || null;
      this._draft.display.host = value("#display-host") || null;
      this._draft.display.mdc_pin = value("#display-pin") || null;
      this._draft.display.mac = value("#display-mac") || null;
      this._draft.display.renderer_url = value("#renderer-url") || null;
      // Missing means on (store.py): an installation from before the switch
      // must not fall silent because the checkbox was not on the page yet.
      const push = root.querySelector("#display-push");
      if (push) this._draft.display.push_enabled = !!push.checked;
    }
  }
}

if (!customElements.get("epaperengine-panel")) {
  customElements.define("epaperengine-panel", EPaperEnginePanel);
}
