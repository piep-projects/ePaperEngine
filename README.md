# ePaperEngine

Home Assistant integration that drives a **Samsung EM32DX colour e-paper panel**
(2560×1440, Spectra 6) as a household wall display: a family calendar, recipes
while you cook, photos, and a greeting when guests arrive.

> 🇩🇪 [Deutsche Fassung dieser Seite](README.de.md)

## How it fits together

ePaperEngine comes in two halves that share one name:

| | What it does |
|---|---|
| **Integration** (this repository, via HACS) | holds the configuration, resolves which view belongs on the wall, keeps the recipe cache, reports the state — panel and Lovelace card |
| **Add-on** (separate repository) | renders the view to HTML/CSS, screenshots it with Chromium, dithers it to the Spectra 6 palette and pushes it to the panel over MDC |

The split is not a preference: a custom integration may only ship pure Python
packages, and rendering needs Chromium and Node. An add-on is its own container
and may carry both.

Everything runs locally — MDC over TLS on port 1515 with a PIN. No cloud, no
vendor account, and the display needs no internet access.

## Requirements

- Home Assistant 2024.7 or newer
- A Samsung EM32DX (“Samsung EMDX 306P”) reachable on your LAN, content source
  set to *Mobile*
- The ePaperEngine add-on, for rendering and pushing

## Installation

1. In HACS, add this repository as a custom repository of type *Integration*.
2. Install **ePaperEngine** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → ePaperEngine.**
4. Configure the display, views and schedules in the **ePaperEngine** panel in
   the sidebar.

## Language

The interface follows your Home Assistant language. English is the base
language; German is a fully maintained translation. Adding another language
means adding two JSON files — `custom_components/epaperengine/translations/`
for the Home Assistant strings and `custom_components/epaperengine/frontend_i18n/`
for the panel and card — and no code change at all.

## Status

Early. This release is the installable skeleton: the integration loads, keeps
its stores and serves the translation catalogs. Entities, panel, card and the
render cycle follow.

## License

MIT — see [LICENSE](LICENSE).
