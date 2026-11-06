"""Offline unit tests for the static preflight checks helper."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from campaign.driver import preflight


def write_config(path: Path, **overrides) -> Path:
    config = {
        "devfoundry_url": "http://10.89.195.201:30861",
        "devfoundry_email_placeholder": "<operator-email>",
        "password_source": "<operator-controlled-secret-file-or-env>",
        "campaign_id": "opsledger-run-001",
        "project_placeholder": "<df-project-name>",
        "repo_placeholder": "<df-repo-name-or-url>",
        "base_branch": "main",
        "mode": "implement",
        "autonomy": "workspace",
        "environment": "polyglot",
        "request_char_limit": 20000,
        "patch_line_target": 400,
        "task_timeout_seconds": 1800,
        "validation_timeout_seconds": 300,
        "default_list_size": 25,
        "max_list_size": 100,
    }
    config.update(overrides)
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


class TestPreflight(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.config_path = write_config(self.root / "config.json")
        campaign = self.root / "campaign"
        for directory in ("requests", "journal", "evidence", "acceptance", "platform_cases", "reports"):
            (campaign / directory).mkdir(parents=True, exist_ok=True)
        (self.root / "check.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (self.root / "README.md").write_text("# bootstrap\n", encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# guardrails\n", encoding="utf-8")

    def by_name(self, checks, name):
        for check in checks:
            if check.name == name:
                return check
        raise AssertionError(f"check '{name}' not found in {[c.name for c in checks]}")

    def test_all_ok_on_qualified_workspace(self):
        checks = preflight.collect_static_preflight(self.config_path, self.root)
        self.assertEqual(
            [(c.name, c.status) for c in checks],
            [
                ("devfoundry_url", "ok"),
                ("password_source", "unknown"),
                ("campaign dirs", "ok"),
                ("bootstrap repo markers", "ok"),
                ("config contamination", "ok"),
            ],
        )
        url_check = self.by_name(checks, "devfoundry_url")
        self.assertEqual(url_check.observed, "http://10.89.195.201:30861")

    def test_placeholder_password_source_unknown_with_note(self):
        checks = preflight.collect_static_preflight(self.config_path, self.root)
        check = self.by_name(checks, "password_source")
        self.assertEqual(check.status, "unknown")
        self.assertIsNotNone(check.note)
        self.assertIn("never store in config", check.note)

    def test_non_placeholder_password_source_is_blocker(self):
        write_config(self.config_path, password_source="file:///home/operator/creds.txt")
        checks = preflight.collect_static_preflight(self.config_path, self.root)
        check = self.by_name(checks, "password_source")
        self.assertEqual(check.status, "blocker")

    def test_missing_campaign_dirs_unknown(self):
        (self.root / "campaign" / "evidence").rmdir()
        (self.root / "campaign" / "reports").rmdir()
        checks = preflight.collect_static_preflight(self.config_path, self.root)
        check = self.by_name(checks, "campaign dirs")
        self.assertEqual(check.status, "unknown")
        self.assertIn("evidence", check.observed)
        self.assertIn("reports", check.observed)

    def test_missing_bootstrap_markers(self):
        (self.root / "AGENTS.md").unlink()
        checks = preflight.collect_static_preflight(self.config_path, self.root)
        check = self.by_name(checks, "bootstrap repo markers")
        self.assertEqual(check.status, "unknown")
        self.assertIn("AGENTS.md", check.observed)

    def test_missing_check_sh_is_blocker(self):
        (self.root / "check.sh").unlink()
        checks = preflight.collect_static_preflight(self.config_path, self.root)
        check = self.by_name(checks, "bootstrap repo markers")
        self.assertEqual(check.status, "blocker")

    def test_bad_url_is_blocker(self):
        write_config(self.config_path, devfoundry_url="ftp://not-http")
        checks = preflight.collect_static_preflight(self.config_path, self.root)
        check = self.by_name(checks, "devfoundry_url")
        self.assertEqual(check.status, "blocker")

    def test_empty_url_is_blocker(self):
        write_config(self.config_path, devfoundry_url="")
        checks = preflight.collect_static_preflight(self.config_path, self.root)
        check = self.by_name(checks, "devfoundry_url")
        self.assertEqual(check.status, "blocker")

    def test_literal_token_value_is_blocker(self):
        write_config(self.config_path, api_key_note="literal-api-token-value")
        checks = preflight.collect_static_preflight(self.config_path, self.root)
        check = self.by_name(checks, "config contamination")
        self.assertEqual(check.status, "blocker")
        self.assertIn("api_key_note", check.observed)

    def test_literal_password_key_is_blocker(self):
        write_config(self.config_path, operator_password="literal-password-placeholder")
        checks = preflight.collect_static_preflight(self.config_path, self.root)
        check = self.by_name(checks, "config contamination")
        self.assertEqual(check.status, "blocker")

    def test_unreadable_config_is_blocker(self):
        checks = preflight.collect_static_preflight(self.root / "missing.json", self.root)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].status, "blocker")
        self.assertEqual(checks[0].name, "config readable")

    def test_write_preflight_report_atomic_markdown(self):
        checks = preflight.collect_static_preflight(self.config_path, self.root)
        out_path = self.root / "campaign" / "reports" / "preflight.md"
        preflight.write_preflight_report(checks, out_path)
        self.assertTrue(out_path.exists())
        leftovers = [p.name for p in out_path.parent.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        content = out_path.read_text(encoding="utf-8")
        self.assertIn("# Campaign static preflight report", content)
        self.assertIn("| devfoundry_url |", content)
        self.assertIn("| ok |", content)
        self.assertIn("| unknown |", content)


if __name__ == "__main__":
    unittest.main()
