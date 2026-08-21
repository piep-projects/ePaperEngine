"""Guard for the manifest the display downloads (FSD §10.1).

This document is the one artefact in the whole system that nobody can debug by
reading it: the panel either takes it or silently shows nothing. Its oddities
were found by reading the source of ``@weejewel/samsung-emdx`` — every ``/``
escaped over the finished string, ``file_size`` as a *string*, three fields that
pretend to be the phone app — and every one of them is the kind of detail a
well-meaning cleanup removes. Hence a test.

Pure stdlib, like ``test_translations.py``: ``delivery`` keeps Pillow behind
``TYPE_CHECKING`` so this runs on a bare CI runner.
"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "addon-epaperengine"))

import delivery  # noqa: E402


class TestContentJson(unittest.TestCase):
    """The shape the EM32DX was proven to accept on 2026-08-19."""

    def setUp(self) -> None:
        self.raw = delivery.build_content_json(
            image_url="http://192.168.178.98:8099/image", image_size=1_356_913
        )
        self.text = self.raw.decode("utf-8")
        self.document = json.loads(self.text)
        self.content = self.document["schedule"][0]["contents"][0]

    def test_every_slash_is_escaped(self) -> None:
        """The original does a blunt ``replaceAll('/', '\\\\/')``. So do we."""
        self.assertNotIn("http://", self.text)
        self.assertIn("http:\\/\\/", self.text)
        # Escaped only once — a double escape would reach the panel as a literal
        # backslash and break the URL.
        self.assertNotIn("\\\\/", self.text)

    def test_escaping_survives_a_json_parse(self) -> None:
        """``\\/`` is legal JSON, so the panel sees the plain URL again."""
        self.assertEqual(self.content["image_url"], "http://192.168.178.98:8099/image")

    def test_file_size_is_a_string(self) -> None:
        self.assertIsInstance(self.content["file_size"], str)
        self.assertEqual(self.content["file_size"], "1356913")

    def test_file_id_is_an_uppercase_uuid(self) -> None:
        file_id = self.content["file_id"]
        self.assertEqual(file_id, file_id.upper())
        self.assertEqual(len(file_id), 36)
        self.assertEqual(self.document["id"], file_id)

    def test_file_name_and_path_carry_the_id(self) -> None:
        file_id = self.content["file_id"]
        self.assertEqual(self.content["file_name"], f"{file_id}.png")
        self.assertEqual(
            self.content["file_path"],
            f"{delivery.CONTENT_FILE_PATH}/{file_id}/{file_id}.png",
        )

    def test_id_is_new_on_every_push(self) -> None:
        """[Festlegung A3] — the phone app does it, so the caching question never arises."""
        other = json.loads(delivery.build_content_json("http://x/image", 1).decode())
        self.assertNotEqual(
            self.content["file_id"], other["schedule"][0]["contents"][0]["file_id"]
        )

    def test_the_fields_that_pretend_to_be_the_phone_app(self) -> None:
        self.assertEqual(self.document["program_id"], "com.samsung.ios.ePaper")
        self.assertEqual(self.document["deploy_type"], "MOBILE")
        self.assertEqual(self.document["content_type"], "ImageContent")

    def test_duration_is_taken_over_unread(self) -> None:
        """Commented ``// TODO ?`` in the original — unexplained, kept verbatim."""
        self.assertEqual(self.content["duration"], 91326)

    def test_schedule_window_is_open_ended(self) -> None:
        window = self.document["schedule"][0]
        self.assertEqual(window["start_date"], "1970-01-01")
        self.assertEqual(window["stop_date"], "2999-12-31")


class TestBestEffortMediaCopy(unittest.TestCase):
    """FSD §3.4: a NAS that is away must not fail an otherwise good run."""

    def test_failure_is_reported_but_not_raised(self) -> None:
        # A path under a *file* can never be created — the cheapest stand-in for
        # an unavailable network share.
        blocker = pathlib.Path(__file__)
        warning = delivery.copy_to_media([(b"x", blocker / "nested" / "current.png")])
        self.assertIsNotNone(warning)
        self.assertIn("media copy failed", str(warning))

    def test_success_reports_nothing(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "wall" / "current.png"
            self.assertIsNone(delivery.copy_to_media([(b"payload", target)]))
            self.assertEqual(target.read_bytes(), b"payload")


if __name__ == "__main__":
    unittest.main()
