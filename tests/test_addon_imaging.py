"""Guards for the image chain and the photo cache (FSD §5, §7, §8.3).

Skipped where Pillow is missing, so a bare CI runner still runs the rest of the
suite. The add-on image always has it.

The test that carries the most weight is ``test_a_second_gamma_pass_moves_the
_picture``: it is the measurement that made the photo cache store *crops*
instead of the dithered results FSD §8.3 asks for. If that test ever goes green
with a tolerance of zero, the deviation can be undone.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "addon-epaperengine"))

try:
    from PIL import Image

    import imaging
    from photocache import PhotoCache

    HAVE_PILLOW = True
except ImportError:  # pragma: no cover - exercised only on a bare runner
    HAVE_PILLOW = False


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed")
class TestCrop(unittest.TestCase):
    """2560×1440 exactly, whatever went in (FSD §3.3: the panel is 1:1)."""

    def test_a_tall_source_is_trimmed_top_and_bottom(self) -> None:
        result = imaging.crop_to_canvas(Image.new("RGB", (3000, 3000)))
        self.assertEqual(result.size, imaging.CANVAS)

    def test_a_wide_source_is_trimmed_left_and_right(self) -> None:
        result = imaging.crop_to_canvas(Image.new("RGB", (6000, 1000)))
        self.assertEqual(result.size, imaging.CANVAS)

    def test_a_source_already_in_ratio_only_scales(self) -> None:
        result = imaging.crop_to_canvas(Image.new("RGB", (3840, 2160)))
        self.assertEqual(result.size, imaging.CANVAS)

    def test_top_share_decides_where_the_trim_comes_off(self) -> None:
        """A gradient makes the offset visible: 0.0 keeps the top edge."""
        source = Image.new("RGB", (1600, 1600))
        for y in range(1600):
            for x in range(0, 1600, 400):  # coarse, this only needs to be readable
                source.putpixel((x, y), (y % 256, 0, 0))
        keep_top = imaging.crop_to_canvas(source, top_share=0.0)
        keep_bottom = imaging.crop_to_canvas(source, top_share=1.0)
        self.assertNotEqual(keep_top.getpixel((0, 0)), keep_bottom.getpixel((0, 0)))


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed")
class TestDither(unittest.TestCase):
    def test_only_the_six_primaries_survive(self) -> None:
        source = Image.new("RGB", (64, 64), (140, 90, 200))
        result = imaging.dither_spectra(source)
        used = {colour for _count, colour in result.getcolors(1 << 16)}
        self.assertTrue(
            used <= set(imaging.SPECTRA), f"off-palette colours reached the panel: {used}"
        )

    def test_gamma_brightens(self) -> None:
        """0.85 < 1 lifts the midtones — the value measured at the panel."""
        grey = Image.new("RGB", (8, 8), (100, 100, 100))
        lut = [min(255, round(255 * ((i / 255) ** imaging.GAMMA))) for i in range(256)]
        self.assertGreater(lut[100], 100)
        # And it is applied, not merely defined.
        flat = imaging.dither_spectra(grey, gamma=1.0)
        lifted = imaging.dither_spectra(grey)
        self.assertNotEqual(flat.tobytes(), lifted.tobytes())

    def test_a_second_gamma_pass_moves_the_picture(self) -> None:
        """Why the cache holds crops, not dithered files (deviation from §8.3).

        Measured 2026-08-21 on 2560×1440: a second gamma-plus-dither pass changes
        1.8 % of the pixels. If the cache stored dithered images, the run's own
        dithering step would apply gamma a second time to every photo.
        """
        source = Image.linear_gradient("L").convert("RGB")
        once = imaging.dither_spectra(source)
        twice = imaging.dither_spectra(once)
        self.assertNotEqual(
            once.tobytes(),
            twice.tobytes(),
            "if these are equal, FSD §8.3 can be followed literally",
        )

    def test_dithering_twice_without_gamma_is_stable(self) -> None:
        """The palette itself is a fixed point — only the gamma is not."""
        source = Image.linear_gradient("L").convert("RGB")
        once = imaging.dither_spectra(source, gamma=1.0)
        twice = imaging.dither_spectra(once, gamma=1.0)
        self.assertEqual(once.tobytes(), twice.tobytes())


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed")
class TestPreview(unittest.TestCase):
    def test_it_is_a_jpeg_of_the_asked_for_size(self) -> None:
        import io

        payload = imaging.preview_bytes(
            Image.new("RGB", imaging.CANVAS, (30, 140, 70)), imaging.PREVIEW_CURRENT
        )
        with Image.open(io.BytesIO(payload)) as small:
            self.assertEqual(small.size, imaging.PREVIEW_CURRENT)
            self.assertEqual(small.format, "JPEG")


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed")
class TestPhotoCache(unittest.TestCase):
    """Content hash in, deterministic order out (FSD §5, §8.3)."""

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self._tmp.name)
        self.source = root / "photos"
        self.source.mkdir()
        self.cache = PhotoCache(
            source=self.source,
            processed=root / "processed",
            preview=root / "preview",
            memo_path=root / "memo.json",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _put(self, name: str, colour: tuple[int, int, int]) -> pathlib.Path:
        path = self.source / name
        Image.new("RGB", (3000, 2000), colour).save(path, format="JPEG", quality=90)
        return path

    def test_it_caches_crops_at_panel_resolution(self) -> None:
        self._put("a.jpg", (10, 20, 30))
        report = self.cache.refresh()
        self.assertEqual((report.total, report.added), (1, 1))
        with Image.open(self.cache.photos[0].crop) as cached:
            self.assertEqual(cached.size, imaging.CANVAS)

    def test_two_copies_of_one_picture_collapse(self) -> None:
        """The identity is the content hash, so a duplicate is not a second slot."""
        self._put("a.jpg", (10, 20, 30))
        import shutil

        shutil.copy(self.source / "a.jpg", self.source / "copy.jpg")
        report = self.cache.refresh()
        self.assertEqual(report.total, 2, "both files are listed")
        self.assertEqual(
            len({photo.digest for photo in self.cache.photos}), 1, "but share one crop"
        )

    def test_a_deleted_source_takes_its_crop_with_it(self) -> None:
        self._put("a.jpg", (10, 20, 30))
        self._put("b.jpg", (200, 10, 10))
        self.cache.refresh()
        (self.source / "b.jpg").unlink()
        report = self.cache.refresh()
        self.assertEqual(report.total, 1)
        self.assertEqual(report.removed, 2, "the crop and its thumbnail")

    def test_the_slot_picks_deterministically_and_wraps(self) -> None:
        self._put("a.jpg", (10, 20, 30))
        self._put("b.jpg", (200, 10, 10))
        self.cache.refresh()
        self.assertEqual(self.cache.pick(0).source, self.cache.pick(2).source)
        self.assertNotEqual(self.cache.pick(0).source, self.cache.pick(1).source)

    def test_an_empty_folder_says_so(self) -> None:
        self.cache.refresh()
        with self.assertRaises(LookupError):
            self.cache.pick(0)

    def test_a_broken_file_does_not_cost_the_album(self) -> None:
        self._put("good.jpg", (10, 20, 30))
        (self.source / "broken.jpg").write_bytes(b"not an image at all")
        report = self.cache.refresh()
        self.assertEqual(report.total, 1)
        self.assertEqual(len(report.unreadable), 1)

    def test_non_images_are_ignored(self) -> None:
        self._put("good.jpg", (10, 20, 30))
        (self.source / "notes.txt").write_text("shopping list")
        (self.source / ".DS_Store").write_bytes(b"\x00")
        self.assertEqual(self.cache.refresh().total, 1)


if __name__ == "__main__":
    unittest.main()
