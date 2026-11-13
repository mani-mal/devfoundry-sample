"""Unit tests for the static file allowlist module (T015 part A)."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from opsledger.http import (
    DEFAULT_ALLOWED_TYPES,
    StaticFile,
    read_static,
    resolve_static,
)
from opsledger.http.envelope import InputError


class ResolveStaticTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name) / "web"
        (self.root / "css").mkdir(parents=True)
        (self.root / "js").mkdir()
        (self.root / "index.html").write_bytes(b"<html>index</html>")
        (self.root / "css" / "styles.css").write_bytes(b"body { color: red; }")
        (self.root / "js" / "app.mjs").write_bytes(b"console.log('app');")

    def test_t1_index_file_with_html_content_type_for_root_and_named(self):
        expected = (self.root / "index.html").resolve()
        for url_path in ("/", "/index.html"):
            resolved = resolve_static(self.root, url_path)
            self.assertEqual(resolved.absolute_path, str(expected))
            self.assertEqual(resolved.content_type, "text/html; charset=utf-8")

    def test_t2_css_and_mjs_resolve_with_their_content_types(self):
        css = resolve_static(self.root, "/css/styles.css")
        mjs = resolve_static(self.root, "/js/app.mjs")
        self.assertEqual(css.content_type, "text/css; charset=utf-8")
        self.assertEqual(css.absolute_path, str((self.root / "css" / "styles.css").resolve()))
        self.assertEqual(mjs.content_type, "text/javascript; charset=utf-8")
        self.assertEqual(mjs.absolute_path, str((self.root / "js" / "app.mjs").resolve()))

    def test_t3_traversal_paths_raise_not_found_404(self):
        for url_path in ("/../secret.txt", "/a/../../secret.txt", "/etc/passwd"):
            with self.assertRaises(InputError) as ctx:
                resolve_static(self.root, url_path)
            self.assertEqual(ctx.exception.code, "not_found")
            self.assertEqual(ctx.exception.status, 404)

    def test_t4_symlink_inside_tree_pointing_outside_is_refused(self):
        other_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(other_tmp.cleanup)
        outside = pathlib.Path(other_tmp.name) / "outside.txt"
        outside.write_bytes(b"outside secret")
        link_path = self.root / "link.html"
        link_path.symlink_to(outside)
        self.assertTrue(link_path.is_symlink())
        with self.assertRaises(InputError) as ctx:
            resolve_static(self.root, "/link.html")
        self.assertEqual(ctx.exception.code, "not_found")
        self.assertEqual(ctx.exception.status, 404)

    def test_t5_missing_file_raises_identical_error_shape(self):
        with self.assertRaises(InputError) as ctx:
            resolve_static(self.root, "/missing.html")
        self.assertEqual(ctx.exception.code, "not_found")
        self.assertEqual(ctx.exception.status, 404)
        with self.assertRaises(InputError) as traversal:
            resolve_static(self.root, "/../secret.txt")
        self.assertEqual(traversal.exception.code, traversal_code := ctx.exception.code)
        self.assertEqual(traversal_code, "not_found")
        self.assertEqual(traversal.exception.status, traversal_status := ctx.exception.status)
        self.assertEqual(traversal_status, 404)

    def test_t6_a_directory_path_raises_identical_error_shape(self):
        with self.assertRaises(InputError) as ctx:
            resolve_static(self.root, "/css")
        self.assertEqual(ctx.exception.code, "not_found")
        self.assertEqual(ctx.exception.status, 404)

    def test_t7_unknown_suffix_sql_file_is_never_servable(self):
        (self.root / "data.sql").write_bytes(b"SELECT 1;")
        with self.assertRaises(InputError) as ctx:
            resolve_static(self.root, "/data.sql")
        self.assertEqual(ctx.exception.code, "not_found")
        self.assertEqual(ctx.exception.status, 404)

    def test_t8_read_static_bytes_and_vanished_file_raises_404(self):
        resolved = resolve_static(self.root, "/css/styles.css")
        self.assertEqual(read_static(resolved), b"body { color: red; }")
        (self.root / "css" / "styles.css").unlink()
        with self.assertRaises(InputError) as ctx:
            read_static(resolved)
        self.assertEqual(ctx.exception.code, read_shape := "not_found")
        self.assertEqual(read_shape, "not_found")
        self.assertEqual(ctx.exception.status, 404)

    def test_t9_read_static_above_max_bytes_raises_500_internal(self):
        big = self.root / "big.bin"
        big.write_bytes(b"ab")
        oversized = StaticFile(
            absolute_path=str(big), content_type="application/octet-stream"
        )
        with self.assertRaises(InputError) as ctx:
            read_static(oversized, max_bytes=1)
        self.assertEqual(ctx.exception.status, 500)
        self.assertEqual(ctx.exception.code, "internal_error")


if __name__ == "__main__":
    unittest.main()
