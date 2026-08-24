# Automations & services

## The Lovelace card

Add a card of type `custom:epaperengine-card` to any dashboard. It shows what is
on the wall, why that view was chosen, when the last push happened — and carries
the five view chips, so switching the wall does not need the sidebar panel.

```yaml
type: custom:epaperengine-card
```

The card resource is registered automatically; there is nothing to add under
**Settings → Dashboards → Resources**.

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
