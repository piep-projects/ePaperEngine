# Recipes

Up to three recipes on the wall at once, each one complete: title, the
ingredients, the method. Cooking from the wall means never wiping flour off a
tablet.

The recipes come from **[Paprika 3](https://www.paprikaapp.com/)**, synced into
a local cache. Nothing is fetched while rendering — the wall does not wait on
somebody's cloud.

## Connecting the account

Panel → **Settings → Paprika account**: the e-mail address and password of your
Paprika account, and how often to sync (24 hours by default).

The sync is incremental: one request asks for `{uid: hash}` over the whole
collection, and only the recipes whose hash changed are fetched in full.

!!! warning "Paprika bans by IP"
    A handful of failed logins is enough. Type the password carefully — there
    is no rapid retry here.

Recipes in Paprika's **trash** are filtered out. They come back from the API
like any other recipe — same uid, full text, distinguished only by a flag — and
without that filter a deleted draft stands next to the real thing in the search.

## Choosing what to cook

Panel → **Recipes**. Search by any word in the title, ingredients or method;
the search ignores accents and case, so `grießbrei`, `GRIESSBREI` and
`griessbrei` all find the same thing.

Every hit says what will happen to it on the wall, for each of the three
possible layouts:

```
1: 28 px · 2: 26 px · 3: shortened
```

That is not a guess. The same layout model that the renderer uses is copied
into the integration, byte for byte, so the panel can promise what the wall will
do.

## Scaling the servings

Each selected recipe carries a target number of people next to the number it was
written for. Change it and the amounts are scaled.

Only the **ingredient list** is scaled, and only the amount at the *start* of a
line — an amount buried in the method text is a Paprika data problem, not
something to rewrite silently. There is no rounding beyond one decimal:
`187.5 g butter` is honest, `190 g` would be an invention. Lines that open with
a word rather than a number — salt, pepper — are left alone.

Roughly one recipe in four has no serving count recorded in Paprika at all, and
those simply do not offer the field.

## How three recipes fit on one wall

The panel is 2560 px wide. **One** recipe gets all of it, **two** get half each,
**three** get a third each — the wall is never left a third blank because only
two dishes are planned.

Within its column each recipe is fitted independently, in steps: **28 px → 26 px
→ 24 px**, and if 24 px still does not fit, the **method is shortened** and says
so at the cut. The ingredient list is never shortened, and the title never.

The ingredient list also splits into two or three columns when the entries are
short enough to stand it, which is usually where the room for the method comes
from.

None of this is estimated. The character width was measured from the exact font
file Chromium draws with, and the line model was checked against Chromium over
twenty real methods: it is within one line, and never optimistic enough to cut
something off.
