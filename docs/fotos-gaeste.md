# Photos & guests

Two views that share the same machinery: a folder of pictures, cropped to 16:9,
dithered onto six colours, cached so no run ever waits on the NAS.

## Photos

Put photos in `<media root>/photos/`. That is the whole curation interface —
there is no album, no tagging, no picker. What is in the folder is what can
appear.

Panel → **Photos** sets how often the picture changes
(`rotation_interval_min`, 60 by default) and shows the cache.

**The rotation is derived from the clock**, not drawn at random: which photo is
due follows from the current time divided by the interval. A stray render run
therefore does not change the picture — random choice would burn a visible
refresh every time anybody pressed a button.

New files are noticed on the next cache pass. **Reload the cache** on the photos
page reads the folder again straight away.

Photos are tracked by the **hash of their content**, not by filename, so
renaming a file on the NAS does not make it a new photo.

## Guests

A greeting in a script face over a background of your choosing — for the
weekend visitors, the birthday party, the neighbours coming for dinner.

Panel → **Guests**:

| | |
|---|---|
| **Name** | the big line, e.g. "The Bergers" |
| **Greeting** | the smaller line under it |
| **Background** | from `<media root>/backgrounds/` |
| **Font** | Dancing Script, Caveat or Great Vibes — all three ship with the add-on |
| **Sizes** | a wish, in pixels; a long name shrinks to fit and is never cut |
| **Colour** | one of the six primaries |
| **Angle** | ±45° |
| **Outline** | off by default; 2–32 px in a contrasting colour |

**The colours are six, and there is no colour picker.** Anything else is
dithered out of the primaries, and along the edge of a letter that is a
speckled outline rather than a shade.

**The outline is what makes a greeting work over any background.** White script
over a dark photo carries by itself; over a bright sky it does not, and 8 px of
white edge fixes it without covering anything up. It is drawn so the stroke
grows *outward* — drawn the other way it eats the thin strokes of the letters.

The size fitting has two adjustments, not one, and both failed alone when
tried: squeezing only the width budget breaks more lines and makes the block
*taller*; squeezing only the font size sets a 52-character name at 40° as one
enormous line where two comfortable ones would have fitted. What still does not
fit is reported as `cramped` in the run log rather than being swallowed by
`overflow: hidden`.

### Switching guest mode off

Guest mode is exempt from the automatic fallback — visitors stay for the
weekend, not four hours. So it has to be ended explicitly, and **whoever may
switch it on may switch it off**: the Lovelace card carries the line, and the
`set_guests` service does it from an automation.

A background whose file has vanished costs the picture, not the run. The
greeting still goes up — the visitors are already in the hall.
