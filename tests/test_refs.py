"""Exercise the reference-containment guard — the skill's central safety promise.

Runs with plain `python -m unittest` (or pytest); no API key, no network. Each test
builds a throwaway refs root under a temp dir so nothing touches the real ~/generations.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import refs  # noqa: E402


class ContainmentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name) / "generations" / "refs"
        root.mkdir(parents=True)
        # Point the module at the temp root for the duration of the test.
        self._orig_root = refs.REFS_ROOT
        refs.REFS_ROOT = root.resolve()
        self.root = refs.REFS_ROOT
        # A valid reference inside the library.
        (self.root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 32)
        # A secret sitting outside the library — must never be readable.
        self.secret = Path(self._tmp.name) / "passport.jpg"
        self.secret.write_bytes(b"\xff\xd8\xff" + b"SENSITIVE" * 4)

    def tearDown(self):
        refs.REFS_ROOT = self._orig_root
        self._tmp.cleanup()

    def test_valid_relative_reference_is_read(self):
        data, mime = refs.resolve_reference("logo.png")
        self.assertEqual(mime, "image/png")
        self.assertTrue(data.startswith(b"\x89PNG"))

    def test_relative_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            refs.resolve_reference("../../passport.jpg")

    def test_arbitrary_absolute_path_is_rejected(self):
        # The old fail-open bug: an absolute path outside every registered set.
        with self.assertRaises(ValueError):
            refs.resolve_reference(str(self.secret))

    def test_absolute_path_inside_a_registered_set_is_allowed(self):
        set_dir = Path(self._tmp.name) / "brand-assets"
        set_dir.mkdir()
        (set_dir / "mark.webp").write_bytes(b"RIFF....WEBP" + b"y" * 16)
        data, mime = refs.resolve_reference(
            str(set_dir / "mark.webp"), allowed_roots=[set_dir]
        )
        self.assertEqual(mime, "image/webp")

    def test_symlink_escape_is_rejected(self):
        link = self.root / "sneaky.jpg"
        try:
            os.symlink(self.secret, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not available on this platform/privilege level")
        with self.assertRaises(ValueError):
            refs.resolve_reference("sneaky.jpg")

    def test_non_image_type_is_rejected(self):
        (self.root / "notes.txt").write_text("hi")
        with self.assertRaises(ValueError):
            refs.resolve_reference("notes.txt")

    def test_oversize_reference_is_rejected(self):
        big = self.root / "huge.png"
        big.write_bytes(b"\x89PNG" + b"0" * (refs.MAX_REF_BYTES + 1))
        with self.assertRaises(ValueError):
            refs.resolve_reference("huge.png")

    def test_missing_file_is_rejected(self):
        with self.assertRaises(ValueError):
            refs.resolve_reference("does-not-exist.png")


if __name__ == "__main__":
    unittest.main()
