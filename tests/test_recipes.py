"""The recipe cache and the Paprika client (FSD §9).

Two things are worth testing without a network, and both are the kind of thing
that fails quietly:

* **the search** (FSD §9.3) — it is the whole selection mechanism. C12 threw out
  a dropdown and a text field in its favour, so "Grieß" not finding *Grießbrei*
  is not a rough edge, it is the feature missing.
* **the parsing** — the Paprika API is undocumented and reverse engineered
  (``paprika.py`` names its sources). Everything that reads its answers is
  written to survive a shape that differs from what was documented, and that
  survival is only real if it is exercised.

What is deliberately **not** tested here: the requests themselves. Nothing in
this repository may talk to the live API in a test — the endpoint is documented
to ban by IP (FSD §9.2), and a test suite is exactly the thing that would run
into that.

Neither ``homeassistant`` nor ``aiohttp`` is installed on the CI runner, so both
are stubbed in ``sys.modules`` before the import — the same trade
``test_resolve.py`` makes.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import sys
import types
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _install_stubs() -> None:
    """Enough of ``homeassistant`` and ``aiohttp`` for the two modules to import.

    Only the names touched at import time, plus the exception type the client
    catches. Anything that would actually reach the network is absent on
    purpose: a test that accidentally started making requests should fail with
    ``AttributeError`` rather than with an IP ban.
    """
    if "aiohttp" in sys.modules:
        return

    aiohttp = types.ModuleType("aiohttp")

    class ClientError(Exception):
        pass

    class ClientTimeout:
        def __init__(self, total: float | None = None) -> None:
            self.total = total

    class FormData:
        def __init__(self) -> None:
            self.fields: dict[str, str] = {}

        def add_field(self, name: str, value: str) -> None:
            self.fields[name] = value

    aiohttp.ClientError = ClientError  # type: ignore[attr-defined]
    aiohttp.ClientTimeout = ClientTimeout  # type: ignore[attr-defined]
    aiohttp.ClientSession = object  # type: ignore[attr-defined]
    aiohttp.FormData = FormData  # type: ignore[attr-defined]
    sys.modules["aiohttp"] = aiohttp

    package = types.ModuleType("homeassistant")
    const = types.ModuleType("homeassistant.const")

    class Platform(str):
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        SENSOR = "sensor"

    const.Platform = Platform  # type: ignore[attr-defined]

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object  # type: ignore[attr-defined]

    helpers = types.ModuleType("homeassistant.helpers")
    storage = types.ModuleType("homeassistant.helpers.storage")

    class Store:  # noqa: D401 - a placeholder, never used by these tests
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

    storage.Store = Store  # type: ignore[attr-defined]
    client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    client.async_get_clientsession = lambda hass: None  # type: ignore[attr-defined]

    util = types.ModuleType("homeassistant.util")
    dt = types.ModuleType("homeassistant.util.dt")
    dt.utcnow = lambda: None  # type: ignore[attr-defined]
    dt.parse_datetime = lambda value: None  # type: ignore[attr-defined]
    util.dt = dt  # type: ignore[attr-defined]

    for name, module in (
        ("homeassistant", package),
        ("homeassistant.const", const),
        ("homeassistant.core", core),
        ("homeassistant.helpers", helpers),
        ("homeassistant.helpers.storage", storage),
        ("homeassistant.helpers.aiohttp_client", client),
        ("homeassistant.util", util),
        ("homeassistant.util.dt", dt),
    ):
        sys.modules[name] = module


def _install_component_package() -> None:
    """``epaperengine.<module>`` without running the package initialiser.

    The real ``__init__`` pulls in half of Home Assistant. A bare namespace
    package with the right ``__path__`` reaches the leaf modules and nothing
    else — the same boundary ``test_resolve.py`` holds.
    """
    if "epaperengine" in sys.modules:
        return
    package = types.ModuleType("epaperengine")
    package.__path__ = [str(REPO_ROOT / "custom_components" / "epaperengine")]  # type: ignore[attr-defined]
    sys.modules["epaperengine"] = package


_install_stubs()
_install_component_package()

from epaperengine import paprika, recipes  # noqa: E402


CACHE = {
    "recipes": {
        "u1": {
            "uid": "u1",
            "name": "Grießbrei",
            "ingredients": "Milch\nGrieß",
            "directions": "Kochen.",
            "categories": ["c1"],
        },
        "u2": {
            "uid": "u2",
            "name": "Apple cake",
            "ingredients": "Apples",
            "directions": "Bake.",
            "categories": ["c2"],
        },
        "u3": {
            "uid": "u3",
            "name": "Zwiebelkuchen",
            "ingredients": "Zwiebeln",
            "directions": "Backen.",
            "categories": [],
        },
    },
    "categories": {"c1": "Nachtisch", "c2": "Baking"},
}


class TestSearch(unittest.TestCase):
    def test_an_empty_query_lists_the_collection(self) -> None:
        """So the panel has something to show before anybody types."""
        self.assertEqual(len(recipes.search(CACHE, "")), 3)

    def test_it_is_case_and_accent_blind(self) -> None:
        """Nobody reaches for the ß key on a phone to find tonight's dinner."""
        for query in ("grießbrei", "GRIESSBREI", "griessbrei"):
            self.assertEqual([hit["uid"] for hit in recipes.search(CACHE, query)], ["u1"], query)

    def test_categories_are_searchable_too(self) -> None:
        self.assertEqual([hit["uid"] for hit in recipes.search(CACHE, "Baking")], ["u2"])

    def test_every_word_has_to_match_in_any_order(self) -> None:
        self.assertEqual([hit["uid"] for hit in recipes.search(CACHE, "cake apple")], ["u2"])
        self.assertEqual(recipes.search(CACHE, "apple onion"), [])

    def test_hits_are_sorted_by_name(self) -> None:
        self.assertEqual(
            [hit["name"] for hit in recipes.search(CACHE, "")],
            ["Apple cake", "Grießbrei", "Zwiebelkuchen"],
        )

    def test_the_limit_holds(self) -> None:
        self.assertEqual(len(recipes.search(CACHE, "", limit=2)), 2)

    def test_a_hit_carries_what_the_panel_shows(self) -> None:
        hit = recipes.search(CACHE, "Grieß")[0]
        self.assertEqual(hit["categories"], ["Nachtisch"])
        self.assertEqual(hit["chars"], len("Grießbrei") + len("Milch\nGrieß") + len("Kochen."))

    def test_an_empty_cache_is_no_hits_and_no_exception(self) -> None:
        self.assertEqual(recipes.search({}, "anything"), [])
        self.assertEqual(recipes.search(recipes.empty_document(), ""), [])


class TestSelection(unittest.TestCase):
    def test_the_order_is_the_column_order(self) -> None:
        picked = recipes.selected(CACHE, ["u3", "u1"])
        self.assertEqual([recipe["name"] for recipe in picked], ["Zwiebelkuchen", "Grießbrei"])

    def test_a_recipe_deleted_in_paprika_drops_out_silently(self) -> None:
        """It must not take the whole wall down — the column falls away."""
        self.assertEqual(len(recipes.selected(CACHE, ["u1", "gone", "u2"])), 2)

    def test_three_is_the_ceiling(self) -> None:
        self.assertEqual(len(recipes.selected(CACHE, ["u1", "u2", "u3", "u1"])), 3)


class TestEnvelope(unittest.TestCase):
    def test_the_documented_envelope_is_unwrapped(self) -> None:
        self.assertEqual(paprika.unwrap({"result": [1, 2]}), [1, 2])

    def test_a_bare_answer_is_taken_as_is(self) -> None:
        """A wrong guess about the wrapper must not cost a working sync."""
        self.assertEqual(paprika.unwrap([1, 2]), [1, 2])

    def test_an_error_becomes_an_exception_with_its_message(self) -> None:
        with self.assertRaises(paprika.PaprikaError) as caught:
            paprika.unwrap({"error": {"message": "Invalid purchase receipt."}})
        self.assertIn("purchase receipt", str(caught.exception))

    def test_a_bare_error_string_works_too(self) -> None:
        with self.assertRaises(paprika.PaprikaError):
            paprika.unwrap({"error": "nope"})


class TestDecode(unittest.TestCase):
    def test_plain_json(self) -> None:
        self.assertEqual(paprika.decode(b'{"a": 1}'), {"a": 1})

    def test_a_gzipped_body_without_the_header(self) -> None:
        """Reported for parts of this API — aiohttp only unwraps a declared one."""
        self.assertEqual(paprika.decode(gzip.compress(json.dumps({"a": 1}).encode())), {"a": 1})

    def test_rubbish_says_what_it_saw(self) -> None:
        with self.assertRaises(paprika.PaprikaError) as caught:
            paprika.decode(b"<html>502 Bad Gateway</html>")
        self.assertIn("502", str(caught.exception))


class TestTrim(unittest.TestCase):
    def test_only_the_fields_the_wall_needs_survive(self) -> None:
        """Photos and nutrition would be carried through every store write."""
        trimmed = paprika.trim_recipe(
            {
                "uid": "u1",
                "name": "Brot",
                "ingredients": "Mehl",
                "directions": "Backen",
                "servings": "4",
                "total_time": "2 h",
                "categories": ["c1"],
                "hash": "abc",
                "photo": "x" * 5000,
                "nutritional_info": "…",
            }
        )
        self.assertEqual(
            set(trimmed), {*paprika.RECIPE_FIELDS, "hash"}
        )
        self.assertNotIn("photo", trimmed)

    def test_a_missing_field_becomes_an_empty_string_not_none(self) -> None:
        """``None`` would reach the template and print the word "None"."""
        trimmed = paprika.trim_recipe({"uid": "u1"})
        self.assertEqual(trimmed["name"], "")
        self.assertEqual(trimmed["directions"], "")
        self.assertEqual(trimmed["categories"], [])

    def test_something_that_is_not_a_recipe_is_skipped(self) -> None:
        for junk in ({}, {"name": "no uid"}, "string", None, 42):
            self.assertIsNone(paprika.trim_recipe(junk), junk)


class TestIndex(unittest.TestCase):
    def test_uid_to_hash(self) -> None:
        self.assertEqual(
            paprika.index_entries([{"uid": "a", "hash": "1"}, {"uid": "b", "hash": "2"}]),
            {"a": "1", "b": "2"},
        )

    def test_entries_without_a_uid_are_dropped(self) -> None:
        self.assertEqual(paprika.index_entries([{"hash": "1"}, "junk", None]), {})

    def test_categories(self) -> None:
        self.assertEqual(
            paprika.category_names([{"uid": "c1", "name": "Baking"}, {"uid": "c2"}]),
            {"c1": "Baking"},
        )


if __name__ == "__main__":
    unittest.main()
