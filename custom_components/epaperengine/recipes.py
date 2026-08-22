"""The recipe cache and the search over it (FSD §9).

**The cache lives where the search lives: in the integration** [Festlegung C11].
A separate sync layer would only pay off if something other than the renderer
read the recipe data, and there is nothing. So: the panel searches locally
without a proxy hop, and the add-on gets the full text of the *selected*
recipes handed to it in the render document — it never talks to Paprika itself.

Two rules the specification makes non-negotiable (FSD §9.2):

* **never per render run** — IP bans for API traffic are documented. Syncing is
  on its own clock (``recipes.sync_interval_h``) plus an explicit button.
* **the result must be visible** — the moment of the last sync and the number of
  recipes are what turn "are the new recipes here yet?" from a guess into an
  answer. They are the state and the attributes of
  ``sensor.epaperengine_recipe_cache``.

The sync is **incremental**: one request fetches ``{uid: hash}`` for the whole
collection, and a detail request only follows for a uid whose hash changed. A
household that adds one recipe therefore costs two requests, not two hundred.

Storage is a third HA store next to config and state. [ungeprüft] whether that
holds up for very large collections — a ``Store`` writes the whole file on every
change (FSD §9.1); the fallback, if it ever complains, is a plain file next to
it.
"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import recipe_layout
from .const import STORAGE_VERSION, STORE_RECIPES
from .paprika import TRASH_FIELD, PaprikaClient, PaprikaError

_LOGGER = logging.getLogger(__name__)

# Politeness towards an endpoint that is documented to ban by IP: a pause
# between two detail requests, and a ceiling on how many one sync may make. A
# first sync of a large collection therefore finishes over several runs instead
# of arriving as a burst — the cache reports how many are still missing.
DETAIL_PAUSE_S = 0.15
DETAIL_LIMIT = 400

SEARCH_LIMIT = 40

# Layout of the cached document. Raised when the *meaning* of what is stored
# changes, not when a field is added: the cache is then dropped and refetched,
# which costs one sync and is the only way to fix a document whose entries are
# wrong rather than missing.
#   2 — recipes in Paprika's trash are no longer cached (measured 2026-08-22:
#       the sync API answers them like any other recipe, and a collection with
#       three deleted drafts showed each of them in the search).
CACHE_FORMAT = 2

# What FSD §8.2 allows on the wall at once. The panel enforces it too, but the
# store is where it has to hold: three columns is a layout constant, not a
# preference.
MAX_SELECTION = 3


def fold(text: str) -> str:
    """Casefold and strip accents, so ``Grieß`` finds ``griess``… almost.

    Almost, because ``ß`` casefolds to ``ss`` while ``ü`` decomposes to ``u`` —
    which is what a German household typing on a phone keyboard actually wants.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def search(
    document: dict[str, Any],
    query: str,
    limit: int = SEARCH_LIMIT,
    slots: int = MAX_SELECTION,
) -> list[dict[str, Any]]:
    """Full-text search over the cache — name and categories (FSD §9.3).

    A pure function over the stored document, like ``resolve.py``: the whole
    search is testable without Home Assistant, a network or a store.

    Every whitespace-separated word of the query has to match somewhere ("apple
    cake" finds *Grandma's apple cake*, in either order); an empty query lists
    the collection so the panel has something to show before anyone types.
    """
    recipes = (document or {}).get("recipes") or {}
    categories = (document or {}).get("categories") or {}
    words = [fold(word) for word in str(query or "").split()]

    hits: list[dict[str, Any]] = []
    for uid, recipe in recipes.items():
        if not isinstance(recipe, dict):
            continue
        names = [str(categories.get(c, c)) for c in (recipe.get("categories") or [])]
        haystack = fold(" ".join([str(recipe.get("name") or ""), *names]))
        if any(word not in haystack for word in words):
            continue
        hits.append(
            {
                "uid": uid,
                "name": str(recipe.get("name") or uid),
                "categories": names,
                # What the wall has to fit into one column (FSD §8.2). Handed
                # out so the panel can warn *before* the picture is rendered;
                # the binding decision about type size and truncation is the
                # add-on's (``recipe_layout.py``).
                "chars": recipe_length(recipe),
                # What the wall is expected to do with it (see ``forecast``).
                "fit": forecast(recipe, slots),
            }
        )
    hits.sort(key=lambda hit: fold(hit["name"]))
    return hits[:limit]


def recipe_length(recipe: dict[str, Any]) -> int:
    """Characters a recipe puts into its column — the number FSD §8.2 budgets."""
    return sum(
        len(str(recipe.get(field) or ""))
        for field in ("name", "ingredients", "directions")
    )


# --- the forecast for the panel -----------------------------------------------
def forecast(recipe: dict[str, Any], slots: int = MAX_SELECTION) -> str:
    """``"28"``, ``"26"``, ``"24"`` or ``"cut"`` — what the wall will do with it.

    **The same code the add-on renders with.** ``recipe_layout.py`` is a copy of
    the add-on's own module, kept byte-identical by ``scripts/publish.py`` and
    guarded by ``tests/test_shared.py``. The first version of this forecast was
    a coarse re-implementation, and it did exactly what a second copy of a model
    does: it told the user a recipe would be shortened while the wall was
    rendering it in full, because it did not know the ingredient list splits
    into sub-columns.

    ``slots`` is how many recipes will share the screen — one gets the whole
    2.400 px, two get 1.180 px each, three get 773 px. The panel asks for
    "this one **plus** what is already picked", which is the question somebody
    looking at the hit list is actually asking.
    """
    slots = min(max(int(slots or 1), 1), MAX_SELECTION)
    column = recipe_layout.build_column(
        recipe,
        width=recipe_layout.slot_width(slots),
        columns=recipe_layout.sub_columns(slots),
    )
    return "cut" if column.truncated else str(column.font_px)


def selected(document: dict[str, Any], uids: list[str]) -> list[dict[str, Any]]:
    """The chosen recipes in the chosen order, silently skipping unknown uids.

    Skipping rather than failing on purpose: a recipe deleted in Paprika must
    not take the whole wall down with it — the column simply falls away, and
    the sensor's count is where the disappearance is visible.
    """
    recipes = (document or {}).get("recipes") or {}
    out: list[dict[str, Any]] = []
    for uid in uids[:MAX_SELECTION]:
        recipe = recipes.get(uid)
        if isinstance(recipe, dict):
            out.append(dict(recipe))
    return out


def empty_document() -> dict[str, Any]:
    """The cache before the first sync."""
    return {
        "format": CACHE_FORMAT,
        "synced_at": None,
        "recipes": {},
        "categories": {},
        # ``{uid: hash}`` of the recipes in Paprika's trash. Remembered rather
        # than merely skipped: without it every sync would re-fetch every
        # deleted recipe forever, and the request budget is the one thing this
        # module exists to protect (FSD §9.2).
        "trashed": {},
        "error": None,
        "pending": 0,
    }


class RecipeCache:
    """Owns the cached collection and the conversation with Paprika."""

    def __init__(
        self, hass: HomeAssistant, credentials: Callable[[], dict[str, Any] | None]
    ) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORE_RECIPES)
        self._credentials = credentials
        self.document: dict[str, Any] = empty_document()
        # One sync at a time. The timer and the panel button can arrive
        # together, and two syncs racing would double the request count against
        # the one endpoint that must not be hammered.
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        if stored and int(stored.get("format") or 1) < CACHE_FORMAT:
            # The entries are wrong, not missing — no amount of hash comparison
            # would notice, because the hashes match. Dropping the collection
            # makes the next sync refetch it; at ~0,15 s per recipe that is
            # seconds, and it happens once.
            _LOGGER.info(
                "Recipe cache format %s → %s: dropping the cached collection so "
                "the next sync refetches it",
                stored.get("format") or 1,
                CACHE_FORMAT,
            )
            stored = {k: v for k, v in stored.items() if k not in ("recipes", "trashed")}
            stored["synced_at"] = None
        self.document = {**empty_document(), **stored, "format": CACHE_FORMAT}

    async def _async_save(self) -> None:
        await self._store.async_save(self.document)

    # --- what the front-ends and the sensor read ------------------------------
    @property
    def count(self) -> int:
        return len(self.document.get("recipes") or {})

    @property
    def synced_at(self) -> str | None:
        return self.document.get("synced_at")

    @property
    def error(self) -> str | None:
        return self.document.get("error")

    def status(self) -> dict[str, Any]:
        """The cache in one small dict — for the panel header and the sensor."""
        return {
            "synced_at": self.synced_at,
            "count": self.count,
            "pending": int(self.document.get("pending") or 0),
            # Not a failure and not a gap — the number that explains why the
            # count is smaller than the collection looks in the Paprika app.
            "trashed": len(self.document.get("trashed") or {}),
            "error": self.error,
            "configured": bool(self._login()),
        }

    def search(
        self, query: str, limit: int = SEARCH_LIMIT, slots: int = MAX_SELECTION
    ) -> list[dict[str, Any]]:
        return search(self.document, query, limit, slots)

    def get(self, uids: list[str]) -> list[dict[str, Any]]:
        recipes = self.document.get("recipes") or {}
        return [dict(recipes[uid]) for uid in uids if uid in recipes]

    def selected(self, uids: list[str]) -> list[dict[str, Any]]:
        return selected(self.document, uids)

    # --- sync -----------------------------------------------------------------
    def _login(self) -> tuple[str, str] | None:
        login = self._credentials() or {}
        username = str(login.get("username") or "").strip()
        password = str(login.get("password") or "")
        return (username, password) if username and password else None

    async def async_sync(self) -> dict[str, Any]:
        """Pull what changed since the last sync (FSD §9.2).

        Returns the status dict either way — a failed sync is an answer to
        "what happened", not an exception the panel has to translate.
        """
        credentials = self._login()
        if credentials is None:
            self.document["error"] = "no_credentials"
            await self._async_save()
            return self.status()

        async with self._lock:
            try:
                result = await self._async_sync_locked(*credentials)
            except PaprikaError as exc:
                _LOGGER.warning("Recipe sync failed: %s", exc)
                self.document["error"] = str(exc)
                await self._async_save()
                return self.status()

        await self._async_save()
        return {**self.status(), **result}

    async def _async_sync_locked(self, username: str, password: str) -> dict[str, Any]:
        client = PaprikaClient(async_get_clientsession(self.hass), username, password)
        index = await client.async_index()

        recipes: dict[str, Any] = dict(self.document.get("recipes") or {})
        trashed: dict[str, str] = dict(self.document.get("trashed") or {})
        # Gone from the collection means gone from the cache. Doing this before
        # the fetches keeps a deleted recipe from surviving a sync that hits the
        # request ceiling half way through.
        removed = [uid for uid in recipes if uid not in index]
        for uid in removed:
            recipes.pop(uid, None)
        for uid in [uid for uid in trashed if uid not in index]:
            trashed.pop(uid, None)

        stale = [
            uid
            for uid, digest in index.items()
            if trashed.get(uid) != digest
            and (uid not in recipes or str((recipes[uid] or {}).get("hash") or "") != digest)
        ]
        pending = max(len(stale) - DETAIL_LIMIT, 0)
        fetched = 0
        binned = 0
        for uid in stale[:DETAIL_LIMIT]:
            recipe = await client.async_recipe(uid)
            if recipe is not None:
                if recipe.pop(TRASH_FIELD, False):
                    # A recipe in Paprika's trash answers with its full text
                    # like any other. Remembering its hash is what keeps the
                    # next sync from asking again; emptying the trash removes
                    # the uid from the index and the entry above with it.
                    trashed[uid] = index[uid]
                    recipes.pop(uid, None)
                    binned += 1
                else:
                    recipe["hash"] = index[uid]
                    recipes[uid] = recipe
                    fetched += 1
            if DETAIL_PAUSE_S:
                await asyncio.sleep(DETAIL_PAUSE_S)

        categories = await client.async_categories()

        self.document = {
            "format": CACHE_FORMAT,
            "synced_at": dt_util.utcnow().isoformat(),
            "recipes": recipes,
            "trashed": trashed,
            # An empty answer must not wipe names that already work.
            "categories": categories or self.document.get("categories") or {},
            "error": None,
            "pending": pending,
        }
        _LOGGER.info(
            "Recipe sync: %d in the collection, %d fetched, %d removed, "
            "%d in the trash (%d newly), %d pending",
            len(recipes),
            fetched,
            len(removed),
            len(trashed),
            binned,
            pending,
        )
        return {"fetched": fetched, "removed": len(removed), "trashed": binned}
