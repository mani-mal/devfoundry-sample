"""Tiny placeholder test; real clock tests land with T001."""

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class PackageMarkerTests(unittest.TestCase):
    def test_init_docstring_non_empty(self):
        init_path = ROOT / "opsledger" / "__init__.py"
        self.assertTrue(init_path.is_file())
        self.assertGreater(len(init_path.read_text(encoding="utf-8").strip()), 0)


if __name__ == "__main__":
    unittest.main()
