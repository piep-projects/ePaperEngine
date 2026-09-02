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
| **Kind** | *appointments*, *birthdays* or *public holidays* |

**The kind matters.** A birthday source shows the year count worked out from
the year in the entry, shows only a start time, and — this is the point — is
**exempt from the "hide today's past appointments" filter**. Without that
exemption the same switch would throw a birthday off the wall at 09:16 on the
very morning it is meant to be read.

A **holiday source** has no colour: the cell stays empty and says "none". Why is
below.

### Public holidays

The third kind is the only one whose entries are not *of* the day but *about*
it. A holiday does two things:

- **the day turns red** — the same filled box a Sunday wears;
- **the name stands in a red line of its own** above that day's appointments,
  with no time and no colour bar.

```
┌────────┐
│   03   │  German Unity Day
│   Thu  │  ▌ 10:00   Breakfast at Gran's
└────────┘  ▌ 14:00   Walk
  (red)
```

No "all day" beside it: a holiday has no hour anybody can be late for. And no
colour bar, because a bar carries the colour of a *source* — a holiday belongs
to nobody. For the same reason a holiday source is **not in the legend**.

**Home Assistant's built-in "Holiday" integration is the obvious source**
(*Settings → Devices & Services → Add → Holiday*); it creates a `calendar.*`
entity for a country and region. Any other calendar works just as well.

!!! note "Not a school-holiday calendar"
    A multi-day entry is drawn **on its first day only**. Every public holiday
    is one day long; school holidays or a works shutdown would otherwise turn
    a fortnight of days red, and red would stop meaning anything in particular.
    Put such periods in an ordinary appointment source — there the wall draws
    them as a running stripe.

**A holiday costs almost nothing.** The line is barely half the height of an
appointment, and on a day that holds nothing else it is free: the date box is
taller anyway. Measured against a calendar with four holidays in the Christmas
window: with one appointment a day it costs **no** days of lookahead, with two
it costs one.

**Red now says three things:** Sunday, public holiday — and, if you set it that
way, the colour of a source. To keep them apart, give your appointment sources
blue, green or black.

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

### Writing the count into the calendar

On the wall the page always works the count out **for itself** — it is right
even if you never touch anything here. Which means the calendar entry itself
does not carry it, and on a phone the entry reads as a plain
`Erika Müller (1946)`.

To make a phone read what the wall reads, ePaperEngine writes the suffix into
the entries: on the calendar page, the card **Write anniversaries back** and its
*Write back now* button. And unattended **every night at 00:15**, as long as the
checkbox above it is ticked — it is ticked from the start.

What it does is deliberately narrow:

- **Anniversary sources only**, and only those served over **CalDAV**. A Local
  Calendar or a subscribed ICS cannot be written to; the card says so and leaves
  the other sources alone.
- **The suffix only.** Title, date, time and the yearly recurrence are left
  alone, and the entry keeps its own address — neither a duplicate nor a gap.
- **Only what is out of date.** A count changes exactly once a year, the night
  after the anniversary. On most nights nothing is written at all.
- **No second set of credentials** — it uses the connection your CalDAV
  integration already holds.

!!! note "Why the time of day is fixed"
    The wall looks ahead: an anniversary in January already carries next year's
    count in December. So which number is right changes at a **date boundary**,
    at midnight. A run "every 24 hours" would drift across that boundary and
    land on either side of it; a fixed time shortly after it always lands on the
    same one.

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
