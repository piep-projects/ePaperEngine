# ePaperEngine

A **Samsung EM32DX** — 32 inches of Spectra 6 colour e-paper, 2560 × 1440 — on
the wall, showing what the household actually needs to look at: the shared
calendar, tonight's recipes, family photos, and a greeting when visitors come.

Driven entirely from **Home Assistant**. No Samsung cloud, no VXT subscription,
and the panel never needs an internet connection. That is the point of the
project, not a side effect.

## How it works

The panel has no browser and runs nothing of its own. It is told, over Samsung's
**MDC protocol** on TLS port 1515, to fetch a picture — and the picture is
served by the add-on on the same network.

```
Home Assistant state  →  Jinja template  →  Chromium at 2560×1440
                      →  Floyd–Steinberg onto six colours
                      →  hash compare  →  MDC push  →  the wall
```

A run takes three to six seconds. If the resulting image is byte-identical to
the one already hanging, **nothing is pushed** — an e-paper refresh is visible
and slow, and one that changes nothing is one nobody should have to watch.

## Two parts, one repository

| | What it does | Installed through |
|---|---|---|
| **Integration** | configuration, the sidebar panel, the Lovelace card, the recipe cache, deciding which view is due | HACS |
| **Add-on** | rendering, dithering, serving the image, pushing it to the panel | the Supervisor add-on store |

They are split because a HACS integration may only carry pure Python, and
rendering needs Chromium and Node. Both live in this one repository — HACS and
the Supervisor read different files and do not collide.

## Get started

1. [Install both parts](installation.md)
2. [Point it at the display](display.md)
3. [Decide what goes on the wall when](ansichten.md)
