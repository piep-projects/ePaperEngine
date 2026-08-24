# Installation

Two parts, installed two different ways, from the same repository.

## 1 · The integration, through HACS

ePaperEngine is not (yet) in the HACS default store, so add it as a custom
repository:

1. **HACS → ⋮ → Custom repositories**
2. URL `https://github.com/piep-projects/ePaperEngine`, category **Integration**
3. Find **ePaperEngine** in the list, **Download**, then **restart Home
   Assistant**

After the restart, add it under **Settings → Devices & services → Add
integration → ePaperEngine**. There is nothing to fill in — the config flow
allows exactly one instance and takes no input; everything is configured
afterwards in the panel.

You should now have a sidebar entry **ePaperEngine** and these entities:

| Entity | What it says |
|---|---|
| `sensor.epaperengine_status` | the outcome of the last run |
| `sensor.epaperengine_target_view` | which view is currently due |
| `sensor.epaperengine_recipe_cache` | how many recipes are cached |
| `binary_sensor.epaperengine_display_reachable` | whether the panel answered its last MDC probe |
| `button.epaperengine_refresh` | run and push now |

## 2 · The add-on, through the Supervisor

The **same** repository URL, added in a different place:

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add `https://github.com/piep-projects/ePaperEngine`
3. The store now lists **ePaperEngine** — **Install**, then **Start**

The add-on builds its own container on first install (Chromium, Node and
Pillow); expect a few minutes. It needs no options: the display's address and
PIN are **not** add-on options on purpose — they would sit in plain text in a
file anyone can open from the Supervisor UI. The integration hands them over on
request instead.

!!! note "Why the add-on is not in HACS"
    HACS installs Python packages. The renderer needs a headless Chromium and a
    Node runtime, which only a container can carry.

## 3 · Tell the two about each other

Open the sidebar panel, go to **Settings**, and fill in **Renderer (add-on) ·
Address**:

```
http://homeassistant.local:8099
```

Use the IP if the name does not resolve. That is the address *Home Assistant*
uses to reach the add-on; the address the **display** fetches from is worked out
by the add-on itself, from the route towards the panel.

Then continue with [the display](display.md).

## Where the images live

ePaperEngine reads your photos from, and writes its renderings into, a directory
under Home Assistant's `media` tree:

```
<media root>/
  photos/        your photos — curate by putting files in
  backgrounds/   backgrounds for the guest greeting
  wall/          the last image pushed, full size
  preview/       the panel's preview
  processed/     cropped 16:9 versions, managed automatically
```

`<media root>` defaults to `/media/epaperengine`, and that is right only when
your media directory is local. **Home Assistant mounts network storage as a
subdirectory of `/media`** — a NAS share shows up as `/media/<mount-name>/`, and
`/media` itself is the Home Assistant machine's own disk. Set **Settings →
Source → Media root** to `/media/<mount-name>/epaperengine` if your photos
are on a NAS, or a few hundred photos and their 2560 × 1440 renderings will land
on the VM's system disk.
