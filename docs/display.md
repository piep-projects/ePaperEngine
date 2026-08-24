# The display

ePaperEngine talks to a **Samsung EM32DX** over Samsung's **MDC** protocol —
TLS on TCP port **1515**, authenticated with the panel's six-digit PIN. No
cloud account, no Samsung certificate, no Tizen app on the device.

## What to fill in

Sidebar panel → **Settings → Connection to the panel**:

| Field | What it is |
|---|---|
| **Host** | the panel's IP address on your network |
| **MDC PIN** | the six-digit PIN configured on the panel itself |
| **MAC** | the panel's MAC address, used for wake-on-LAN |

Then press **Test connection**. It does not ping and it does not check whether
a port is open — it opens TLS:1515, authenticates with the PIN and asks the
panel a real question. A green answer means the whole chain works. Model,
firmware, serial number and battery state appear further down the same page.

!!! tip "Give the panel a fixed address"
    Set a **DHCP reservation** for the display in your router. If it picks up a
    new address, every push fails until somebody notices and edits the field —
    and this has happened.

## How a picture gets there

The panel has no browser. It is *told* to fetch:

1. the add-on writes the rendered PNG and a small `content.json` manifest into
   its own storage, and serves both on port 8099
2. over MDC, the add-on sends `set_content_download` with the manifest URL
3. the panel fetches the manifest, then the image, over plain HTTP on the LAN
4. the panel refreshes

The address in the manifest is the add-on's **address as seen from the panel**,
worked out from the network route towards it — not the one you typed into the
settings page, which is only how Home Assistant reaches the add-on. The image is
served from the add-on's own storage rather than from the media tree, so a NAS
that reboots mid-fetch cannot leave the display reaching into thin air.

## Only one instance may push

There is exactly **one** display. If two Home Assistant instances — a test one
and a production one, say — both render and push, they overwrite each other
every quarter of an hour, and the wall flickers between two truths.

**Settings → Push safety** carries the switch:

- **on** — this instance serves the wall (the default for a fresh install)
- **off** — everything is still rendered, the image and preview are still
  written, the panel stays fully usable, and the run reports **`push_off`**.
  Only the MDC push is skipped.

Switching it back on does not push by itself. The next scheduled run will, or
press **Update the wall** on the overview page.

## Anti-ghosting

Colour e-paper keeps a faint memory of what it showed before. The panel has its
own **screen protection** routine, scheduled on the device (03:00 by default).
Its effect over months of a mostly-static calendar has not been measured here —
if you see ghosting, that setting is the first place to look.

## Battery and wake-on-LAN

The EM32DX runs on mains or on its internal battery. The MAC address field
exists so a sleeping panel can be woken with a magic packet before a push.
**Whether wake-on-LAN reaches it reliably over WiFi is untested** — on mains
power the question does not arise.
