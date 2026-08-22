"""Paprika sync API — the only cloud this project accepts (FSD §1, §9.2).

Two halves, deliberately separated:

* the **pure** part — unwrapping the response envelope, decompressing a body,
  cutting a recipe down to the six fields FSD §9.2 names. No network, no Home
  Assistant, therefore testable (``tests/test_paprika.py``).
* the **client** — one login, then Bearer on every call, with a single retry
  when the token has expired.

**Rate limit is a hard constraint** [belegt]: IP bans for too much API traffic
are documented, so nothing here may ever be called per render run. The caller
that enforces that is ``recipes.py``; this module only makes the calls cheap
enough to obey it — the recipe list is one request, and a detail request only
happens for a uid whose ``hash`` actually changed.

**The endpoint facts** — researched from ``johnwbyrd/kappari``
(``authentication.md``/``endpoints.md``) and the ``mattdsteele`` gist, then
**confirmed against the live account on 2026-08-22**: the v1 login, the Bearer
token on the v2 sync endpoints, the ``result`` envelope and the recipe fields
all behave as written here. 57 recipes and 21 categories came back on the first
run:

* ``POST /api/v1/account/login/`` takes ``email`` and ``password`` as
  *multipart* fields and answers ``{"result": {"token": …}}``. The v1 endpoint
  is the portable one on purpose: ``/api/v2/account/login/`` rejects a
  password-only login with *"Invalid purchase receipt."* unless the request
  looks like a licensed mobile client, and this add-on has no license blob to
  send. The token it hands back is accepted by the v2 sync endpoints.
* ``GET /api/v2/sync/recipes/`` answers ``{"result": [{"uid", "hash"}, …]}`` —
  **including the recipes in Paprika's trash.** Measured 2026-08-22 against the
  live account: a deleted recipe keeps its uid, keeps answering, and carries
  ``in_trash: true``. Nothing but that flag tells it apart, and the collection
  it came from had three entries under one name because of it.
* ``GET /api/v2/sync/recipe/{uid}/`` answers ``{"result": {…recipe…}}``.
* ``GET /api/v2/sync/categories/`` answers ``{"result": [{"uid", "name"}, …]}``.
* Bodies may arrive gzip-compressed. ``aiohttp`` unwraps a proper
  ``Content-Encoding: gzip``; the fallback in ``_decode`` is for the case where
  the payload is compressed *without* that header, which the community
  documentation reports for parts of this API.

Anything the service actually answers differently will surface on the first
real sync as a legible error rather than as a wrong picture — that is why
``PaprikaError`` carries the raw text.
"""

from __future__ import annotations

import gzip
import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Login on v1, sync on v2 — see the module docstring for why the two differ.
LOGIN_URL = "https://www.paprikaapp.com/api/v1/account/login/"
API_BASE = "https://www.paprikaapp.com/api/v2"

# The service answers a password-only login differently depending on who asks;
# a client string that names a mobile app is the documented way through.
USER_AGENT = "Paprika Recipe Manager 3/3.3.1 (iPhone; iOS 17.0)"

TIMEOUT = aiohttp.ClientTimeout(total=45)

# What the cooking view needs (FSD §9.2). Everything else the service sends —
# photos, nutrition, ratings, source URLs — is dropped at the door rather than
# carried through the store: the cache is written back whole on every sync, and
# a photo blob per recipe would make that write the expensive part.
RECIPE_FIELDS = (
    "uid",
    "name",
    "ingredients",
    "directions",
    "servings",
    # FSD §9.2 names ``total_time``; the wall shows the two halves as well
    # [Festlegung 2026-08-22] — "20 min Vorbereitung, 40 min Kochen" tells the
    # cook something the sum does not, and Paprika keeps all three.
    "prep_time",
    "cook_time",
    "total_time",
    "difficulty",
    "categories",
)

# Not a wall field — a verdict. Carried out of ``trim_recipe`` so the cache can
# drop the recipe without a second request, and named here rather than inlined
# because "the answer contains deleted recipes" is the kind of fact that gets
# lost in a nested ``get``.
TRASH_FIELD = "in_trash"


class PaprikaError(RuntimeError):
    """Any failure of the sync API, with enough text to act on."""


class PaprikaAuthError(PaprikaError):
    """Login refused, or a token that is no longer accepted."""


# --- pure helpers -------------------------------------------------------------
def decode(body: bytes) -> Any:
    """Bytes → JSON, transparently un-gzipping a body that needs it."""
    try:
        return json.loads(body)
    except ValueError:
        pass
    try:
        return json.loads(gzip.decompress(body))
    except (OSError, ValueError, EOFError) as exc:
        snippet = body[:200].decode("utf-8", "replace")
        raise PaprikaError(f"unreadable answer: {snippet}") from exc


def unwrap(payload: Any) -> Any:
    """Take the ``result`` out of the envelope, or raise what is in ``error``.

    Tolerant about the envelope itself: the documented shape is
    ``{"result": …}``, but a bare list or object is accepted rather than
    rejected. A wrong guess about the wrapper should not cost a working sync.
    """
    if isinstance(payload, dict):
        error = payload.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else error
            raise PaprikaError(str(message))
        if "result" in payload:
            return payload["result"]
    return payload


def trim_recipe(raw: Any) -> dict[str, Any] | None:
    """Cut one recipe down to the fields of FSD §9.2.

    ``None`` for anything that is not a recipe — a stray entry must not take
    the whole sync down with it. ``ingredients`` and ``directions`` stay
    **multi-line free text**: they are not structured lists at Paprika [belegt],
    so portion scaling would need parsing and is not in scope (FSD §8.2).

    ``in_trash`` rides along, and the caller is expected to act on it: a
    recipe in the trash still answers with its full text, so without the flag
    a deleted draft sits in the search looking exactly like the recipe that
    replaced it [gemessen 2026-08-22].
    """
    if not isinstance(raw, dict) or not raw.get("uid"):
        return None
    recipe = {field: raw.get(field) for field in RECIPE_FIELDS}
    recipe["categories"] = [str(c) for c in (raw.get("categories") or []) if c]
    # The service's own checksum, kept so the next sync can skip this recipe.
    recipe["hash"] = raw.get("hash")
    recipe[TRASH_FIELD] = bool(raw.get(TRASH_FIELD))
    for field in (
        "name",
        "ingredients",
        "directions",
        "servings",
        "prep_time",
        "cook_time",
        "total_time",
        "difficulty",
    ):
        value = recipe.get(field)
        recipe[field] = "" if value is None else str(value)
    return recipe


def index_entries(raw: Any) -> dict[str, str]:
    """``[{uid, hash}, …]`` → ``{uid: hash}``, the shape the cache compares."""
    entries: dict[str, str] = {}
    for item in raw or ():
        if isinstance(item, dict) and item.get("uid"):
            entries[str(item["uid"])] = str(item.get("hash") or "")
    return entries


def category_names(raw: Any) -> dict[str, str]:
    """``[{uid, name}, …]`` → ``{uid: name}``.

    Best effort by design: the search shows category names as a reading aid
    (FSD §3.1), and a sync that fails only here is still a good sync.
    """
    names: dict[str, str] = {}
    for item in raw or ():
        if isinstance(item, dict) and item.get("uid") and item.get("name"):
            names[str(item["uid"])] = str(item["name"])
    return names


# --- the client ---------------------------------------------------------------
class PaprikaClient:
    """One account, one token, one session.

    The session belongs to Home Assistant (``async_get_clientsession``) — this
    class never opens one of its own, so it holds no resource that a reload
    would have to clean up.
    """

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None

    async def async_login(self) -> str:
        """Fetch a token. Raises ``PaprikaAuthError`` on wrong credentials."""
        form = aiohttp.FormData()
        form.add_field("email", self._username)
        form.add_field("password", self._password)
        try:
            async with self._session.post(
                LOGIN_URL,
                data=form,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            ) as response:
                body = await response.read()
                if response.status in (401, 403):
                    raise PaprikaAuthError(f"login refused (HTTP {response.status})")
                if response.status >= 400:
                    raise PaprikaError(
                        f"login failed: HTTP {response.status}: "
                        f"{body[:200].decode('utf-8', 'replace')}"
                    )
        except aiohttp.ClientError as exc:
            raise PaprikaError(f"cannot reach Paprika: {exc}") from exc

        try:
            result = unwrap(decode(body))
        except PaprikaError as exc:
            # An ``error`` in the envelope of a *login* is a credentials problem,
            # and the panel says something different for those.
            raise PaprikaAuthError(str(exc)) from exc
        token = (result or {}).get("token") if isinstance(result, dict) else None
        if not token:
            raise PaprikaAuthError("login answered without a token")
        self._token = str(token)
        return self._token

    async def _get(self, path: str) -> Any:
        """GET one sync endpoint, logging in first and once more on a 401."""
        for attempt in (1, 2):
            if not self._token:
                await self.async_login()
            try:
                async with self._session.get(
                    f"{API_BASE}{path}",
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "User-Agent": USER_AGENT,
                    },
                    timeout=TIMEOUT,
                ) as response:
                    body = await response.read()
                    if response.status in (401, 403):
                        # An expired token, most likely. Drop it and try once —
                        # never in a loop: wrong credentials would otherwise
                        # hammer the endpoint that bans by IP.
                        self._token = None
                        if attempt == 1:
                            continue
                        raise PaprikaAuthError(f"{path}: HTTP {response.status}")
                    if response.status >= 400:
                        raise PaprikaError(
                            f"{path}: HTTP {response.status}: "
                            f"{body[:200].decode('utf-8', 'replace')}"
                        )
            except aiohttp.ClientError as exc:
                raise PaprikaError(f"{path}: {exc}") from exc
            return unwrap(decode(body))
        raise PaprikaError(f"{path}: gave up after a retry")  # pragma: no cover

    async def async_index(self) -> dict[str, str]:
        """``{uid: hash}`` of the whole collection — **one** request."""
        return index_entries(await self._get("/sync/recipes/"))

    async def async_recipe(self, uid: str) -> dict[str, Any] | None:
        """One recipe, trimmed to the fields the wall needs."""
        return trim_recipe(await self._get(f"/sync/recipe/{uid}/"))

    async def async_categories(self) -> dict[str, str]:
        """``{uid: name}``; an empty map when the endpoint does not play along."""
        try:
            return category_names(await self._get("/sync/categories/"))
        except PaprikaError as exc:
            _LOGGER.info("Categories unavailable, continuing without them: %s", exc)
            return {}
