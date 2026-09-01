# Troubleshooting

## Read the status first

`sensor.epaperengine_status` says how the last run ended, and the panel's
overview page says the same thing in words.

| State | What it means | What to do |
|---|---|---|
| `unchanged` | rendered, the picture is identical, nothing sent | nothing — this is the normal outcome |
| `pushed` | rendered and sent | nothing |
| `push_off` | rendered, but this instance is not allowed to push | Settings → Push safety, if that is not intended |
| `push_failed` | the picture is ready, the panel did not answer | see below |
| `render_failed` | no picture at all | see below |
| `idle` | no run since installation | press **Update the wall** |

## The wall shows nothing new

**First check whether anything *should* be new.** `unchanged` after a run means
the picture really is the same. If you changed an appointment on your phone, the
calendar page's **Sync now** pulls the sources immediately instead of waiting up
to 15 minutes.

If the picture on the **preview** in the panel is right but the wall is not, the
display missed a push — press **Send the picture again** on the overview. That
one ignores the hash comparison, which is exactly the difference between the two
buttons.

## An update is installed, the wall looks the same as before

**Almost always the second half is missing.** ePaperEngine is an integration and
an add-on, updated separately — and **HACS only reports the integration**. The
image, though, is drawn by the **add-on**: layout, type, colours and page
structure live there, not in the integration.

**Two steps, and the second is the one that gets forgotten.**

**1 · Update the add-on.** The Supervisor only learns about the new version once
it re-reads the repository — until then the add-on page offers **no update at
all**, only the "auto update" switch. From a terminal:

```bash
ha store reload
ha apps info efa2b8da_epaperengine | grep version
```

If `ha store reload` aborts with `context deadline exceeded`, that is **not a
failure** — half a minute later the new version is there.

`ha apps info` prints **two** lines, and the difference between them is the
point:

```
version: 0.20.1          ← what is running
version_latest: 0.21.1   ← what is waiting
```

When they differ, the repository has been re-read and the update is **ready but
not installed**. The command that installs it:

```bash
ha apps update efa2b8da_epaperengine
```

It rebuilds the container and takes a minute or two; afterwards both lines show
the same version. (The button on the add-on page does the same thing.)

**2 · Have a new image drawn.** An add-on update draws nothing by itself; the
wall keeps the picture from before. **Panel → Overview → "Send image again".**
Without this step a correctly installed update looks as if it had not taken
effect — and you go looking for the fault in the wrong place.

**Rule of thumb: if the wall looks different, it was the add-on.** If something
about the controls changed, it was the integration. Full description under
[Installation](installation.md#updating-both-halves).

## `push_failed` — the panel does not answer

1. **Settings → Test connection.** It opens TLS:1515 and authenticates; the
   error message it prints is the real one.
2. **Has the display changed address?** This is the usual cause. Set a DHCP
   reservation for it.
3. **Is the PIN still right?** A factory reset of the panel resets it.
4. **Is the display asleep or flat?** The battery percentage is on the same
   settings page.

## `render_failed` — no picture at all

The technical line on the error page, and `sensor.epaperengine_status`, name the
view that failed. That tells a repeated failure of one view from a system
failing at everything.

- **Is the add-on running?** Settings → Add-ons → ePaperEngine. Its log is the
  one to read.
- **Is the renderer address right?** Settings → Renderer (add-on) → Address.
  `http://homeassistant.local:8099`, or the IP if the name does not resolve.
- **Is the media directory reachable?** A NAS that is away takes photos and
  guest backgrounds with it. The calendar and recipes do not need it.

## The panel is blank / the sidebar entry does nothing

Reload the browser with the cache bypassed (Ctrl+Shift+R). If it stays blank,
the browser console will have the reason — and if the entry is there while the
page is empty, the JavaScript failed to run rather than failing to load.

## Nothing was found in Paprika

- Check the account under **Settings → Paprika account** and press **Sync now**
  on the recipes page; it reports the time and the count.
- **Careful with retries.** Paprika bans by IP after a handful of failed
  logins.
- Recipes in Paprika's trash are filtered out on purpose. If a recipe has
  vanished from the search, check whether it was deleted on a phone.

## A recipe is being shortened

Expected, and it says so. With three recipes side by side, a good half of a
typical collection does not fit in full. Cook two at a time and most of them
fit; cook one and almost everything does.

The ingredient list and the title are never shortened — only the method, and it
says where it was cut.

## The wall refreshes far too often

Every visible refresh comes from a picture that really changed. If it happens
every 15 minutes on the dot, something on the page is carrying the current time.
This was true of the calendar until the timestamp in its foot was removed —
which is why there is no timestamp on any view now.

## The wall is in the wrong language

It follows Home Assistant's own language setting
(**Settings → System → General**). There is no separate switch.
