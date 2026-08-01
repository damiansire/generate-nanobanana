"""Exercise save_generation — the never-overwrite media+sidecar contract."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from save import save_generation  # noqa: E402


class SaveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_writes_media_and_sidecar_pair(self):
        sidecar = {"model": "m", "prompt": "p", "params": {}}
        path = save_generation(b"\x89PNG", ".png", "hero", self.out, sidecar)
        self.assertTrue(path.exists())
        self.assertEqual(path.name, "hero.png")
        side = self.out / "hero.json"
        self.assertTrue(side.exists())
        self.assertEqual(json.loads(side.read_text())["model"], "m")

    def test_never_overwrites_existing_pair(self):
        s = {"model": "m", "prompt": "first", "params": {}}
        first = save_generation(b"a", ".png", "hero", self.out, s)
        second = save_generation(b"b", ".png", "hero", self.out, {**s, "prompt": "second"})
        # The first pair is untouched; the second gets a numeric suffix.
        self.assertEqual(first.name, "hero.png")
        self.assertEqual(second.name, "hero_1.png")
        self.assertEqual(first.read_bytes(), b"a")
        self.assertEqual(json.loads((self.out / "hero.json").read_text())["prompt"], "first")
        self.assertEqual(json.loads((self.out / "hero_1.json").read_text())["prompt"], "second")


if __name__ == "__main__":
    unittest.main()
