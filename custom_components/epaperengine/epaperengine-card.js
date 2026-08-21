/**
 * ePaperEngine — Lovelace dashboard card (FSD §3.1).
 *
 * The daily glance, next to the weather and the house technology: what hangs on
 * the wall, since when, **why**, when it changes next, and five chips to
 * override it. Setting up lives in the sidebar panel; the gear in the header
 * goes there.
 *
 * Three things are deliberately absent [Festlegungen 2026-08-20]:
 *   - **no refresh button** — the timed net runs every 15 min and pushes only on
 *     a changed image hash, so a button would only start what is about to
 *     happen anyway. The rule that follows: no control on this card does merely
 *     what the system does by itself. Hence also no "retry" and no "check
 *     connection".
 *   - **no "display reachable" dot in the normal case** — a lamp that is always
 *     green carries no information. Only the fault reports itself.
 *   - **the preview is collapsed** — the card stays small and grows when asked.
 *
 * Add it with:
 *     type: custom:epaperengine-card
 *     title: ePaperEngine       # optional
 */

const APP_NAME = "ePaperEngine";
const ICON = "mdi:image-frame"; // shared with the sidebar panel (const.py PANEL_ICON)
const PANEL_PATH = "/epaperengine"; // const.py PANEL_URL_PATH
const POLL_MS = 15000;

// The five chips. Order is display order, not priority — the priority list is
// configuration and lives in the panel (FSD §5).
const CHIP_VIEWS = ["calendar", "recipes", "photos", "guests"];
// Run results that put the red strip up (FSD §12). ``unchanged`` is explicitly
// **not** one of them: an image identical to the last is the normal outcome.
const FAULT_RESULTS = new Set(["push_failed", "render_failed"]);

// ---------------------------------------------------------------------------
// i18n (i18n concept §4/§7/§8)
//
// Three independent axes, three signals: language from `hass.language`,
// number/date format from `hass.locale`, units from `hass.config.unit_system`
// (this card formats no units of its own). Translations are *data* — one flat
// JSON catalog per language, fetched at runtime, English as the base.
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
// If *no* catalog can be fetched, the fallback chain would end at the raw key
// and the card would read "card.on_the_wall". These few strings keep the
// always-visible part usable; anything deeper degrades to a humanised key.
const I18N_EMERGENCY = {
  "common.loading": "Loading…",
  "common.error": "Error: {msg}",
  "error.unknown": "Unknown error",
  "error.not_loaded": "ePaperEngine is not set up",
  "card.on_the_wall": "On the wall",
  "card.since": "since {time}",
  "card.last_push": "Last push",
  "card.next_change": "Next change",
  "card.preview.show": "Show preview",
  "card.preview.hide": "Hide preview",
  "card.chip.auto": "Automatic",
  "card.settings": "Settings",
  "view.calendar": "Calendar",
  "view.recipes": "Recipes",
  "view.photos": "Photos",
  "view.guests": "Guests",
  "view.error": "Error",
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

/** Active language → en → emergency → humanised key. Does **not** escape. */
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

/** Clock time in the user's locale — never a hard-coded "de-DE". */
function fmtTime(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  if (isNaN(date)) return null;
  try {
    return new Intl.DateTimeFormat(_fmt.locale, {
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  } catch (e) {
    return date.toISOString().slice(11, 16);
  }
}

/** "2:40 h" / "18 min" — a remaining time, not a clock time. */
function fmtDuration(ms) {
  if (!isFinite(ms) || ms <= 0) return null;
  const minutes = Math.round(ms / 60000);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `${hours}:${String(rest).padStart(2, "0")} h`;
}

/**
 * The "because" line — the reason the resolution picked this view (FSD §5).
 * Without it the priority resolution is a black box to whoever is looking.
 */
function becauseLine(status) {
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
    case "fallback":
    default:
      return t("card.because.fallback");
  }
}

class EPaperEngineCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
    this._status = null;
    this._error = null;
    this._loading = true;
    this._timer = null;
    this._previewOpen = false;
    this._previewUrl = null;
    this._built = false;
    this._onVisible = () => {
      if (!document.hidden) this._load();
    };
  }

  setConfig(config) {
    this._config = config || {};
  }

  /** Collapsed 302 px, expanded 582 px (FSD §3.1) — roughly 6 and 11 rows. */
  getCardSize() {
    return this._previewOpen ? 11 : 6;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
  }

  connectedCallback() {
    this._timer = setInterval(() => this._load(), POLL_MS);
    document.addEventListener("visibilitychange", this._onVisible);
    if (this._hass) this._load();
  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
    document.removeEventListener("visibilitychange", this._onVisible);
  }

  async _call(message) {
    return this._hass.connection.sendMessagePromise(message);
  }

  async _load() {
    if (!this._hass) return;
    try {
      await i18nLoad(this._hass);
      this._status = await this._call({ type: "epaperengine/status" });
      this._error = null;
    } catch (err) {
      this._error = err && (err.message || err.code) ? err.message || t("error.code", { code: err.code }) : t("error.unknown");
    }
    this._loading = false;
    if (this._previewOpen) await this._signPreview();
    this._render();
  }

  /**
   * ``media`` is authenticated, and an `<img>` carries no bearer token — so the
   * path is signed right before use (FSD §15, measured 2026-08-21: the signed
   * URL answers 200, the bare one 401). Signed here rather than in the
   * integration, because a signature has an expiry date and the page that keeps
   * it on screen is the one that has to renew it.
   */
  async _signPreview() {
    const path = this._status && this._status.preview_path;
    if (!path) {
      this._previewUrl = null;
      return;
    }
    try {
      const signed = await this._call({ type: "auth/sign_path", path, expires: 3600 });
      this._previewUrl = signed && signed.path ? signed.path : null;
    } catch (err) {
      this._previewUrl = null;
    }
  }

  async _setView(view) {
    try {
      this._status = await this._call({ type: "epaperengine/set_view", view });
      this._render();
    } catch (err) {
      this._error = (err && err.message) || t("error.unknown");
      this._render();
    }
  }

  _openPanel() {
    history.pushState(null, "", PANEL_PATH);
    window.dispatchEvent(new CustomEvent("location-changed", { bubbles: true, composed: true }));
  }

  async _togglePreview() {
    this._previewOpen = !this._previewOpen;
    if (this._previewOpen && !this._previewUrl) await this._signPreview();
    this._render();
  }

  // --- rendering ------------------------------------------------------------
  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; }
        .head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
        .head .title { flex: 1; font-weight: 600; font-size: 1.05rem; }
        .icon-button {
          background: none; border: none; cursor: pointer; padding: 4px;
          color: var(--secondary-text-color); border-radius: 50%; line-height: 0;
        }
        .icon-button:hover { background: var(--secondary-background-color); }
        .row { display: flex; gap: 10px; align-items: flex-start; }
        .dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 6px; flex: none;
               background: var(--success-color, #43a047); }
        .dot.warn { background: var(--warning-color, #ff9800); }
        .dot.bad { background: var(--error-color, #db4437); }
        .headline { font-weight: 600; }
        .sub { color: var(--secondary-text-color); font-size: 0.87rem; line-height: 1.45; }
        .block { padding: 10px 0; border-bottom: 1px solid var(--divider-color); }
        .block:last-of-type { border-bottom: none; }
        .strip {
          border-left: 4px solid var(--error-color, #db4437);
          background: var(--secondary-background-color);
          padding: 8px 12px; border-radius: 4px; margin-bottom: 12px;
        }
        .strip.warn { border-left-color: var(--warning-color, #ff9800); }
        .strip .headline { margin-bottom: 2px; }
        .toggle {
          background: none; border: none; padding: 6px 0; cursor: pointer;
          color: var(--primary-color); font: inherit; font-size: 0.9rem;
        }
        .preview { width: 100%; border-radius: 6px; display: block;
                   background: var(--secondary-background-color); aspect-ratio: 16 / 9; }
        .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
        .chip {
          border: 1px solid var(--divider-color); border-radius: 16px;
          padding: 5px 14px; background: var(--card-background-color);
          color: var(--primary-text-color); font: inherit; font-size: 0.87rem;
          cursor: pointer;
        }
        .chip:hover { border-color: var(--primary-color); }
        .chip.on { border-color: var(--primary-color); color: var(--primary-color); font-weight: 600; }
        .action {
          width: 100%; margin-top: 12px; padding: 10px; border: none; border-radius: 6px;
          background: var(--primary-color); color: var(--text-primary-color, #fff);
          font: inherit; font-weight: 600; cursor: pointer;
        }
        .muted { color: var(--secondary-text-color); }
      </style>
      <ha-card><div class="body"></div></ha-card>
    `;
    this._built = true;
  }

  _render() {
    if (!this._built) this._build();
    const body = this.shadowRoot.querySelector(".body");
    const title = esc(this._config.title || APP_NAME);
    const head = `
      <div class="head">
        <ha-icon icon="${ICON}"></ha-icon>
        <div class="title">${title}</div>
        <button class="icon-button" id="settings" title="${esc(t("card.settings"))}">
          <ha-icon icon="mdi:cog"></ha-icon>
        </button>
      </div>`;

    if (this._loading) {
      body.innerHTML = `${head}<div class="sub">${esc(t("common.loading"))}</div>`;
      this._wire();
      return;
    }
    if (this._error || !this._status) {
      body.innerHTML = `${head}<div class="strip"><div class="headline">${esc(
        t("common.error", { msg: this._error || t("error.not_loaded") }),
      )}</div></div>`;
      this._wire();
      return;
    }

    const status = this._status;
    body.innerHTML = head + this._faultStrip(status) + this._manualStrip(status) +
      this._wallBlock(status) + this._nextBlock(status) + this._previewBlock(status) +
      this._chips(status);
    this._wire();
  }

  /** Red strip: only a real fault (FSD §12) — "unchanged" is not one. */
  _faultStrip(status) {
    const run = status.last_run || {};
    if (status.addon_error) {
      return `<div class="strip">
        <div class="headline">${esc(t("card.error.addon"))}</div>
        <div class="sub">${esc(status.addon_error)}</div>
      </div>`;
    }
    if (!FAULT_RESULTS.has(status.result)) return "";
    const stillUp = status.last_push
      ? `<div class="sub">${esc(t("card.error.still_showing", { view: viewLabel(run.view) }))}</div>`
      : "";
    return `<div class="strip">
      <div class="headline">${esc(t(`result.${status.result}`))}</div>
      <div class="sub">${esc(run.error || t("card.error.not_pushed"))}</div>
      ${stillUp}
    </div>`;
  }

  /** Orange strip while a view is pinned by hand, with the remaining time. */
  _manualStrip(status) {
    const manual = status.manual;
    if (!manual || !manual.view) return "";
    const left = manual.until ? fmtDuration(new Date(manual.until) - new Date()) : null;
    const line = left
      ? t("card.override.until", { duration: left })
      : t("card.because.manual_open");
    return `<div class="strip warn">
      <div class="headline">${esc(viewLabel(manual.view))}</div>
      <div class="sub">${esc(line)}</div>
    </div>`;
  }

  _wallBlock(status) {
    const target = status.target || {};
    const since = fmtTime((status.manual && status.manual.at) || (status.last_push || {}).at);
    const pushAt = fmtTime((status.last_push || {}).at);
    const dot = FAULT_RESULTS.has(status.result) ? "bad" : status.manual ? "warn" : "";
    const pushLine =
      status.result === "unchanged"
        ? `${t("card.last_push")} ${pushAt || t("common.never")} · ${t("card.image_unchanged")}`
        : `${t("card.last_push")} ${pushAt || t("common.never")}`;
    return `<div class="block row">
      <div class="dot ${dot}"></div>
      <div>
        <div class="headline">${esc(viewLabel(target.view))} — ${esc(t("card.on_the_wall"))}</div>
        <div class="sub">${esc(since ? t("card.since", { time: since }) : "")}${since ? " · " : ""}${esc(becauseLine(status))}</div>
        <div class="sub">${esc(pushLine)}</div>
      </div>
    </div>`;
  }

  _nextBlock(status) {
    if (!status.next_change) return "";
    const time = fmtTime(status.next_change);
    if (!time) return "";
    return `<div class="block">
      <div class="headline">${esc(t("card.next_change"))} ${esc(time)}</div>
    </div>`;
  }

  /** Collapsed by default: the card stays at its small size until asked. */
  _previewBlock(status) {
    const label = this._previewOpen ? t("card.preview.hide") : t("card.preview.show");
    const arrow = this._previewOpen ? "▾" : "▸";
    const image =
      this._previewOpen && this._previewUrl
        ? `<img class="preview" src="${esc(this._previewUrl)}" alt="${esc(viewLabel((status.target || {}).view))}">`
        : this._previewOpen
          ? `<div class="preview"></div>`
          : "";
    return `<div class="block">
      <button class="toggle" id="preview">${arrow} ${esc(label)}</button>
      ${image}
    </div>`;
  }

  _chips(status) {
    const manual = status.manual && status.manual.view;
    const chips = [
      `<button class="chip ${manual ? "" : "on"}" data-view="">${esc(t("card.chip.auto"))}</button>`,
      ...CHIP_VIEWS.map(
        (view) =>
          `<button class="chip ${manual === view ? "on" : ""}" data-view="${view}">${esc(viewLabel(view))}</button>`,
      ),
    ];
    const back = manual
      ? `<button class="action" id="auto">${esc(t("card.override.auto_on"))}</button>`
      : "";
    return `<div class="chips">${chips.join("")}</div>${back}`;
  }

  _wire() {
    const root = this.shadowRoot;
    const settings = root.querySelector("#settings");
    if (settings) settings.onclick = () => this._openPanel();
    const preview = root.querySelector("#preview");
    if (preview) preview.onclick = () => this._togglePreview();
    const auto = root.querySelector("#auto");
    if (auto) auto.onclick = () => this._setView(null);
    root.querySelectorAll(".chip").forEach((chip) => {
      chip.onclick = () => this._setView(chip.dataset.view || null);
    });
  }
}

if (!customElements.get("epaperengine-card")) {
  customElements.define("epaperengine-card", EPaperEngineCard);
}

// Show up in the "Add card" picker rather than only under "Manual".
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "epaperengine-card")) {
  window.customCards.push({
    type: "epaperengine-card",
    name: APP_NAME,
    description: "What hangs on the e-paper wall, why, and what changes it next.",
  });
}
