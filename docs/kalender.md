# Calendar

Three columns, the next days one after another, filled until the page is full.
Whatever is behind a calendar — Microsoft 365 published ICS, Google, CalDAV, the
built-in Local Calendar — never reaches the renderer. ePaperEngine reads Home
Assistant **`calendar` entities**, and that is all it knows about them.

## Adding a source

Panel → **Calendar**. Each source is four things:

| | |
|---|---|
| **Entity** | any `calendar.*` entity |
| **Person** | the name in the legend |
| **Colour** | one of the panel's six primaries |
| **Kind** | *appointments* or *birthdays* |

**The kind matters.** A birthday source shows the year count worked out from
the year in the entry, shows only a start time, and — this is the point — is
**exempt from the "hide today's past appointments" filter**. Without that
exemption the same switch would throw a birthday off the wall at 09:16 on the
very morning it is meant to be read.

### Not only birthdays

The kind is called *birthdays*, but it means **any anniversary** — a wedding
day, a name day, a jubilee. That is why the suffix is neutral:

```
09:00   Erika Müller (1946) — 80 years
09:00   Wedding Ulla & Christian (2006) — 20 years
09:00   Name day Christian
```

**What is being celebrated goes in the title** — the wall only contributes the
number. "Turns 80" would be wrong for a wedding, and the calendar offers no
field the kind could be read from.

**The year goes in brackets in the title:** `Erika Müller (1946)`. Then a phone's
calendar app shows it too, and the wall shows the same thing plus the count.
The **description** carries it as well — four digits and nothing else. Either
one is enough; **both at once** leaves the bracket in the picture on top of the
count.

**A missing year costs the count, not the entry.** A name day has none, and that
is not an error.

## What the page looks like

- **The day sits in a rail on the left**, not in a line above: a filled badge
  with the day number large and the weekday small under it. It is as tall as the
  day and grows with it when a title needs two lines — the type never shrinks.
  That saves the header line every day used to carry, and puts about a third
  more days on the page.
- **Sundays wear a red badge** instead of a black one. A column is read by its
  dates, and a red block is found from across the room.
- **The month is said once at the top**, over the first column. When the month
  turns mid-window, the 1st carries it in its badge — so the date stays right
  across the boundary.
- **A yellow band opens every week**, before each Monday, carrying the week
  number and its date range across the full column width. Yellow because a grey
  on this display is mostly white and therefore looks pale, and because yellow
  is the one colour no calendar source can wear.
- **Legend, error notes and nothing else** sit at the foot of the third column,
  right-aligned. Columns one and two run the full height.
- **A colour bar** in the source's colour runs down each entry — 12 px by
  default, adjustable. At a metre's distance a 6 px bar reads as a mark *beside*
  the line; 12 px reads as the colour *of* the line.
- **Empty days are shown** by default, so the eye can count days rather than
  read them — they carry only their date badge, and the space beside it stays
  white. Switchable.
- **A multi-day appointment is named at both ends and drawn as an unbroken
  colour stripe in between** — even when it is not entered as all-day. The first
  day says "from 10:00", the last "until 15:00", and between them a continuous
  line in the source's colour runs down the outer edge, through the gaps between
  days and across any week band. An appointment that ends before 6 in the
  morning stays **one** entry on its own evening instead: a concert from 23:00
  to 01:00 is not an appointment on the next day.
- **A day taller than a whole column** is cut and says so, rather than being
  skipped — skipping it would silently drop that day *and everything after it*.

!!! note "What the running stripe costs"
    The days between start and end **no longer name the appointment**. Looking
    at one of them shows the stripe, and you have to follow it upwards. In
    exchange a fortnight's holiday no longer fills fourteen day blocks but two —
    so it costs the look-ahead almost nothing.

## What it does not do

**There is no timestamp.** There was one — "updated 10:17" at the foot — and it
carried the minute, which made every calendar image unique. The hash comparison
could then never say `unchanged`, so all four scheduled runs an hour turned into
real pushes with a visible refresh of the wall.

How fresh the page is now shows in the page itself: today's appointments drop
out as the day goes on.

## Refreshing on demand

**Sync now** on the calendar page does three things in one go, because they
are one intention: it pulls every source (`homeassistant.update_entity`, which
ICS sources need), counts the entries again, and kicks off a render run. The run
is *started*, not waited for.

Next to it, **Recount** deliberately does *not* pull — it reports what Home
Assistant already holds. And the sources are pulled at most once every 30
seconds, so the run that "Sync now" starts does not immediately fetch
everything a second time.

The button also says whether the wall is currently showing the calendar at all.
Without that, pressing it while a photo hangs there would look broken.
