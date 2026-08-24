# Dashboard

Everything on this page is about the **Lovelace card** — the daily glance, next
to the weather and the house technology. Setting things up happens in the
sidebar panel; the card is for looking and for the one decision a household
makes daily: *what should be on the wall right now?*

## Adding it

The card registers its own resource, so there is **nothing** to add under
**Settings → Dashboards → Resources**.

1. Open a dashboard, **Edit dashboard → Add card**
2. Search for **ePaperEngine** in the picker

Or in YAML:

```yaml
type: custom:epaperengine-card
```

## Configuration

Two keys, and one of them is the type. There is no visual editor — there is
nothing to configure that is worth one.

| Key | | |
|---|---|---|
| `type` | required | `custom:epaperengine-card` |
| `title` | optional | the heading; defaults to `ePaperEngine` |

```yaml
type: custom:epaperengine-card
title: The wall
```

The card takes no `entity`. It reads the whole state over its own WebSocket
connection and polls every 15 seconds — the same interval the panel uses.

## What it shows

From top to bottom, and most of it only when there is something to say:

**A red strip — only on a real fault.** `push_failed`, `render_failed`, or the
add-on being unreachable. It names the fault, the technical line, and — if a
picture is still hanging — which view that is. **`unchanged` is not a fault**
and never puts the strip up.

**An orange strip while a view is pinned by hand**, with the time left on the
override.

**What is on the wall**: the view, since when, **why** it was chosen (schedule,
manual, guest mode, fallback), and when the last push happened. If the last run
came back `unchanged`, it says so — "image unchanged, nothing pushed" is the
normal outcome, not a warning.

**Next change**, when one is scheduled.

**A guest strip**, when guest mode is on: since when, and the one button that
ends it — *Visitors have left*.

**The preview**, collapsed. The card stays small and grows when asked.

**The chips**: *Automatic*, then Calendar, Recipes, Photos, Guests. Pressing one
overrides the priority for `manual_timeout_h` hours; *Automatic* hands it back
immediately. The error view has no chip — it is not something anyone chooses.

The **gear** in the header opens the sidebar panel.

## What is deliberately not on it

Three absences, and each is a rule rather than an omission:

- **No refresh button.** The timed net runs every 15 minutes and pushes only
  when the image really changed, so the button would only start what is about to
  happen anyway. The rule that follows: *no control on this card does merely
  what the system does by itself* — hence also no "retry" and no "test
  connection". The two wall buttons for the exceptional cases live on the
  panel's overview page.
- **No "display reachable" lamp in the normal case.** A lamp that is always
  green carries no information. Only the fault reports itself.
- **The preview is collapsed.** A dashboard card that is mostly a picture pushes
  everything else off the screen.

The one control that looks like an exception is *Visitors have left*, and it is
not one: guest mode is exempt from the automatic fallback, so **nothing ends it
on its own** — and the Guests chip switches it on for anybody in the house.
Without the counterpart it would be a thing the household can start and only an
administrator can stop.

## Card or panel?

| | |
|---|---|
| **Card** | what is on the wall, and changing it — for everybody, every day |
| **Panel** (sidebar) | calendars, recipe selection, photos, the guest greeting, and every setting — mostly administrator territory |

See [Automations & services](automationen.md) for the entities and services
behind both.
