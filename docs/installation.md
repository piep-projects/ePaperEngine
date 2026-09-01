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
Address** with the **IP address of your Home Assistant instance** and port 8099:

```
http://192.168.1.42:8099
```

**The field is empty on a fresh installation**, and while it stays empty the
integration tries `http://homeassistant.local:8099`. That only works when mDNS
resolves from inside the Home Assistant container — often it does not, and the
log then reads:

```
Cannot connect to host homeassistant.local:8099 [Network unreachable]
```

So the name is a convenience for those it resolves for; the IP is the route that
always carries. (A DHCP reservation for the HA instance keeps the entry from
going stale.)

That is the address *Home Assistant* uses to reach the add-on; the address the
**display** fetches from is worked out by the add-on itself, from the route
towards the panel.

Then continue with [the display](display.md).

## Updating — **both halves**

ePaperEngine is two parts that update **separately**, and this is the most
common trap: **HACS only tells you about the integration.** An update installed
there alone may change **nothing** about what is on the wall — the image is
drawn by the add-on.

| Part | How | What it changes |
|---|---|---|
| **Integration** | HACS reports a new version, then **restart Home Assistant** | panel, card, settings, scheduling, calendar queries |
| **Add-on** | see below — the Supervisor has to re-read the repository first | **the image itself** — layout, type, colours, page structure |

Rule of thumb: **if the wall looks different, it was the add-on.** If something
about the controls changed, it was the integration. After a release, check both
— they carry the same version number.

### The add-on: re-read first, then update

The Supervisor only learns about a new add-on version once it re-reads the
repository — until then the add-on page offers **no update at all**, only the
"auto update" switch. From a terminal (the *Terminal & SSH* or *Advanced SSH &
Web Terminal* add-on):

```bash
ha store reload
ha apps info efa2b8da_epaperengine | grep version
```

`ha store reload` often aborts with `context deadline exceeded`. **That is not a
failure** — the Supervisor keeps reading; half a minute later the new version
shows up under `version_latest`. With "auto update" on it then updates by
itself; otherwise use `ha apps update efa2b8da_epaperengine` or the button on
the add-on page.

### Then have a new image drawn

**An add-on update draws nothing by itself.** The wall keeps the picture from
before and holds it until the next run comes round. If you would rather not
wait: **panel → Overview → "Send image again".** Without that step a correctly
installed update looks as if it had not taken effect.

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
