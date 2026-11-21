"""Static markup checks for web/index.html.

The environment has no real browser; the T076 browser checklist is recorded
separately as manual/not-run, so these automated checks pin the markup the
checklist would start from.
"""

import pathlib
import re
import unittest


class WebMarkupTests(unittest.TestCase):
    def _html(self):
        return (
            pathlib.Path(__file__).resolve().parents[2] / "web" / "index.html"
        ).read_text(encoding="utf-8")

    def test_document_metadata_and_landmark_labels(self):
        html = self._html()
        self.assertIn('<html lang="en">', html)
        self.assertIn('charset="utf-8"', html)
        self.assertIn('name="viewport"', html)
        title = re.search(r"<title>([^<]*)</title>", html)
        self.assertIsNotNone(title)
        self.assertTrue(title.group(1).strip())
        labels = re.findall(r'aria-label="([^"]*)"', html)
        self.assertEqual(len(labels), 2)
        self.assertEqual(len(set(labels)), len(labels))
        for section in re.findall(r"<section [^>]*>", html):
            self.assertIn("aria-label=", section)
            self.assertIn("id=", section)

    def test_no_tabindex_hacks_and_no_inline_handlers(self):
        html = self._html()
        self.assertNotIn("tabindex", html.lower())
        self.assertNotIn("onclick=", html)
        self.assertNotIn("onload=", html)
        without_module = html.replace(
            '<script type="module" src="/js/app.mjs"></script>', ""
        )
        self.assertNotIn("<script>", without_module)
        self.assertIn('type="module"', html)


if __name__ == "__main__":
    unittest.main()
