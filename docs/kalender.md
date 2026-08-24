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

**The kind matters.** A birthday source shows the age worked out from the year
in the entry, shows only a start time, and — this is the point — is **exempt
from the "hide today's past appointments" filter**. Without that exemption the
same switch would throw a birthday off the wall at 09:16 on the very morning it
is meant to be read.

## What the page looks like

- **No header.** The date is said once, by the first day title. A header saying
  it a second time cost 140 px off all three columns, which is 14 % of the
  appointments the page can hold.
- **Legend, error notes and nothing else** sit at the foot of the third column,
  right-aligned. Columns one and two run the full height.
- **A colour bar** in the source's colour runs down each entry — 12 px by
  default, adjustable. At a metre's distance a 6 px bar reads as a mark *beside*
  the line; 12 px reads as the colour *of* the line.
- **Empty days are shown** by default ("no appointments"), so the eye can count
  days rather than read them. Switchable.
- **A day taller than a whole column** is cut and says so, rather than being
  skipped — skipping it would silently drop that day *and everything after it*.

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
