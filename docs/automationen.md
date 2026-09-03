# Automations & services

## The Lovelace card

`custom:epaperengine-card` shows what is on the wall, why that view was chosen
and when the last push happened, and carries the chips for switching it — see
**[Dashboard](dashboard.md)** for adding and configuring it.

## Entities

| Entity | |
|---|---|
| `sensor.epaperengine_status` | `idle` · `pushed` · `unchanged` · `push_failed` · `push_off` · `render_failed` |
| `sensor.epaperengine_target_view` | `calendar` · `recipes` · `photos` · `guests` · `error` |
| `sensor.epaperengine_recipe_cache` | number of cached recipes |
| `binary_sensor.epaperengine_display_reachable` | the last MDC probe |
| `button.epaperengine_refresh` | run and push now |

!!! note "`unchanged` is not a failure"
    It is the most common outcome and the one you want. It means the wall
    already shows the right picture.

`binary_sensor.epaperengine_display_reachable` is not a ping and not a port
check — it reflects a real MDC conversation with the panel, PIN and all.

## Services

### `epaperengine.render`

Render and, if the picture changed, push.

```yaml
action: epaperengine.render
data:
  force: false   # true pushes even when the picture is identical
```

`force: true` is the "send it again" case — a display that missed a push after a
power cut and is stuck on an old picture.

### `epaperengine.set_view`

```yaml
action: epaperengine.set_view
data:
  view: recipes   # calendar · recipes · photos · guests · error
```

Overrides the priority by hand, for `manual_timeout_h` hours.

### `epaperengine.set_guests`

```yaml
action: epaperengine.set_guests
data:
  active: true
```

Switch guest mode on or off. Switching it off also clears a manual override
that was pointing at `guests`.

### `epaperengine.sync_recipes`

Pull the Paprika collection now, outside the normal interval.

### `epaperengine.sync_anniversaries`

```yaml
action: epaperengine.sync_anniversaries
data:
  dry_run: false
```

Writes the year count into the anniversary calendar itself, so a phone shows
what the wall shows: `Erika Müller (1946)` becomes
`Erika Müller (1946) — 80 years`.

Only sources of kind **anniversaries** are touched, and only **CalDAV**
calendars can be written to — a Local Calendar cannot be changed from outside
and is skipped by name. The wall still computes the number itself; the written
suffix is a convenience for the phone, not the source of truth. If this service
fails, or is never set up, the wall is still right.

**`dry_run` defaults to `true`** — the run then reports what it would change and
changes nothing. Switch it off to actually write. `limit: 1` writes at most one
entry, which is a good first attempt.

A daily run is harmless: it reads the calendar and writes back only the entries
whose number is out of date — on most nights that is none.

!!! note "Most of the time you do not need this service"
    Since version 0.23.0 ePaperEngine writes the counts back **by itself, every
    night at 00:15**; the checkbox for it is on the calendar page and is ticked
    from the start. The service is here for a different time of day, or for
    hanging the run off an event of your own.

```yaml
automation:
  - alias: Keep anniversaries current
    triggers:
      - trigger: time
        at: "04:30:00"
    actions:
      - action: epaperengine.sync_anniversaries
        data:
          dry_run: false
```

### `epaperengine.sync_calendars`

```yaml
action: epaperengine.sync_calendars
data:
  dry_run: false
```

Copies the calendars Home Assistant produces — **public holidays** and **waste
collection** — into the CalDAV calendars entered beside them on the calendar
page, a year ahead, so a phone shows what the wall shows.

Only sources of those two kinds that name a sync calendar are touched. The wall
is unaffected either way: it keeps reading the Home Assistant entity, so a run
that fails costs a phone its bin day, not the household its calendar page.

**`dry_run` defaults to `true`** — the run then reports what it would create and
delete and touches nothing. Switch it off to actually sync.

!!! warning "This one deletes"
    The target is a mirror: an entry the source no longer names is **removed**
    from it. Only entries ePaperEngine wrote itself are ever deleted, and only
    within the 365-day window — everything else is counted as "foreign" and left
    alone. Run it once with `dry_run: true` after changing a target and read the
    answer.

!!! note "Most of the time you do not need this service"
    Since version 0.24.0 ePaperEngine syncs **by itself, every night at 00:30**;
    the checkbox for it is on the calendar page and is ticked from the start.

```yaml
automation:
  - alias: Sync the bin days after the collector changed them
    triggers:
      - trigger: state
        entity_id: calendar.waste_collection
    actions:
      - action: epaperengine.sync_calendars
        data:
          dry_run: false
```

## Examples

**A greeting when the doorbell rings during a party**

```yaml
automation:
  - alias: Guests are here
    triggers:
      - trigger: state
        entity_id: input_boolean.party_mode
        to: "on"
    actions:
      - action: epaperengine.set_guests
        data:
          active: true
```

**Recipes on the wall while dinner is being cooked**

```yaml
automation:
  - alias: Kitchen time
    triggers:
      - trigger: time
        at: "17:30:00"
    actions:
      - action: epaperengine.set_view
        data:
          view: recipes
```

Better still: give the `recipes` view a **schedule helper** on the panel's Views
page. Then it is a window rather than a moment, it shows up in the schedule
editor, and nothing has to be un-set afterwards.

**Tell me when the wall has been mute for an hour**

```yaml
automation:
  - alias: The wall is not answering
    triggers:
      - trigger: state
        entity_id: binary_sensor.epaperengine_display_reachable
        to: "off"
        for: "01:00:00"
    actions:
      - action: notify.persistent_notification
        data:
          message: The e-paper panel has not answered for an hour.
```

## Permissions

Most of ePaperEngine is open to everyone signed in to Home Assistant: choosing a
view, switching guest mode, rendering, pushing. Those are the everyday things,
and a household member who may change what hangs on the shared wall may also
redraw it.

**Configuration is administrator-only** — the whole Settings page, the calendar
sources, the recipe selection. The MDC PIN and the Paprika password are never
sent to a non-administrator at all: they come back as a plain "a value is
stored" instead.
