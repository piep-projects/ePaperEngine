"""Guard for the image store's location (FSD §3.4).

The specification writes ``/media/epaperengine/`` as if it were a constant.
Measured on 2026-08-21, it cannot be: Home Assistant mounts network storage as a
*subdirectory* of ``/media`` (``/media/media_test_ocean3/`` on ha-test1), so the
literal path lands on the local disk of the HA machine — not on the NAS the
specification asks for. The root is therefore configuration, and this test keeps
the fallback honest and the folder names English [Festlegung 2026-08-21: renaming
them after the first add-on run would be a migration].
"""

from __future__ import annotations

import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "addon-epaperengine"))

import paths  # noqa: E402


class TestMediaRoot(unittest.TestCase):
    def test_unconfigured_falls_back_to_the_specification_path(self) -> None:
        self.assertEqual(paths.media_paths(None).root, pathlib.Path("/media/epaperengine"))

    def test_a_configured_root_wins(self) -> None:
        layout = paths.media_paths("/media/media_test_ocean3/epaperengine")
        self.assertEqual(
            layout.photos, pathlib.Path("/media/media_test_ocean3/epaperengine/photos")
        )

    def test_the_tree_matches_the_specification(self) -> None:
        layout = paths.media_paths("/root")
        self.assertEqual(
            {
                layout.photos.name,
                layout.backgrounds.name,
                layout.wall.name,
                layout.preview.name,
            },
            {"photos", "backgrounds", "wall", "preview"},
        )
        self.assertEqual(layout.processed_photos, pathlib.Path("/root/processed/photos"))
        self.assertEqual(layout.preview_photos, pathlib.Path("/root/preview/photos"))


class TestSourceFolder(unittest.TestCase):
    def test_defaults_to_photos_under_the_root(self) -> None:
        layout = paths.media_paths("/root")
        self.assertEqual(paths.source_folder(layout, None), pathlib.Path("/root/photos"))

    def test_an_explicit_folder_wins(self) -> None:
        layout = paths.media_paths("/root")
        self.assertEqual(
            paths.source_folder(layout, "/media/elsewhere/album"),
            pathlib.Path("/media/elsewhere/album"),
        )


if __name__ == "__main__":
    unittest.main()
