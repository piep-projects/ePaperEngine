# Views & priority

There are five views. Four of them show something; the fifth appears only when
things go wrong.

| View | What it shows |
|---|---|
| **Calendar** | the next days from any number of Home Assistant calendars, in three columns — see [Calendar](kalender.md) |
| **Recipes** | up to three recipes side by side, in full — see [Recipes](rezepte.md) |
| **Photos** | one photo from your folder, changed on a fixed clock — see [Photos & guests](fotos-gaeste.md) |
| **Guests** | a greeting in a script face over a background — see [Photos & guests](fotos-gaeste.md) |
| **Error** | one sentence, when the wall would otherwise be lying |

## Which one is due

ePaperEngine walks an **ordered list of candidates** from top to bottom and
takes the first one that is *active*. The list is configuration, not code —
sort it on the panel's **Views** page.

| Candidate | active when … |
|---|---|
| `manual` | somebody picked a view by hand and the timeout has not run out |
| `guests` | guest mode is switched on |
| `recipes` | at least one recipe is selected |
| `schedule` | one of the schedule helpers is `on` right now |
| `fallback` | always — it is the end of the list |

The starting order is **manual → guests → recipes → schedule → fallback**.

Only these five can be sorted. `calendar`, `photos` and `error` have no
activity condition of their own, so they could never become "active" — they are
what a **schedule** or the **fallback** points at, not candidates in their own
right.

### Schedules

A view gets a time window by pointing it at a Home Assistant **`schedule`
helper** (Settings → Devices & services → Helpers → Schedule). ePaperEngine does
not build its own calendar of times — the helper already exists, has an editor
and shows up in automations.

Each mapping also carries a **rank**. Overlapping windows are not a mistake:
within the `schedule` candidate the lowest rank wins.

### Setting a view by hand

Anyone in the household can pick a view — from the panel's overview, from the
chips on the Lovelace card, or with the `set_view` service. That override lasts
**`manual_timeout_h`** hours (4 by default; `0` means "until switched back"),
and then the automatic order takes over again.

**Guest mode is exempt from the timeout.** Visitors stay for the weekend, not
for four hours. It is switched off explicitly — the card carries a "the guests
have gone" line, and there is the `set_guests` service.

The fallback runs on its own timer rather than waiting for the next scheduled
run, so "back to automatic in 2 h 48 min" means exactly that and not "up to 15
minutes later".

## When the wall is redrawn

- every **15 minutes**, on the clock
- whenever the resolved view changes
- whenever the photo clock ticks over
- whenever you save something in the panel that changes the picture
- when the `render` service is called, or the refresh button pressed

Two triggers within 20 seconds are collapsed into one run.

**A run does not mean a push.** The rendered image is hashed and compared with
what was last sent; identical means nothing is sent and the run reports
`unchanged`. That is the normal outcome, not a failure.

## When something breaks

The **first** failed run in a row leaves the picture hanging. A NAS briefly away
or one wedged Chromium is not worth taking the family photo down for. From the
**second** in a row the wall shows the failure itself: one sentence, the time
the trouble started, and one technical line.

The timestamp on that page is the **start of the streak**, never the current
run — which is what makes the page identical from run to run, so the hash
comparison suppresses the repeats. A day-long outage costs exactly one refresh.

## What language the wall speaks

Whatever Home Assistant speaks. There is no separate switch — a second language
setting next to the system one is a setting nobody remembers changing. English
and German are both complete.
