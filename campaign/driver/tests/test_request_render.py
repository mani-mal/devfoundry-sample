"""Offline unit tests for the campaign request renderer."""

from __future__ import annotations

import tempfile
import unittest

from campaign.driver import cli_adapter
from campaign.driver import request_render


def full_context() -> dict:
    return {
        "campaign_id": "opsledger-run-001",
        "backlog_id": "B02",
        "title": "Add journal index rebuild",
        "base_commit": "abc1234567890",
        "prerequisites": "B01 bootstrap accepted",
        "goal": "Rebuild the journal projection from complete records.",
        "current_contracts": "campaign.driver.journal.append_event stays stable.",
        "required_change": "Extend campaign/driver/journal.py with rebuild_index.",
        "acceptance": "Unit tests pass via bash check.sh gate.",
        "allowed_paths": "campaign/driver/journal.py, campaign/driver/tests/",
        "constraints": "stdlib-only Python 3.12; no new packages; UTC timestamps.",
        "evidence_expected": "journal events, index.json projection, test output.",
    }


class TestRequestRender(unittest.TestCase):
    def test_full_valid_context_renders(self):
        rendered = request_render.render_request(full_context())
        self.assertIn("Campaign: opsledger-run-001", rendered)
        self.assertIn("Backlog item: B02", rendered)
        self.assertIn("Title: Add journal index rebuild", rendered)
        self.assertIn("Base commit: abc1234567890", rendered)
        self.assertIn("Evidence expected: journal events", rendered)

    def test_rendered_contains_campaign_and_base_commit_labels(self):
        rendered = request_render.render_request(full_context())
        self.assertIn("Campaign:", rendered)
        self.assertIn("Base commit:", rendered)

    def test_missing_placeholder_raises_value_error(self):
        context = full_context()
        del context["goal"]
        with self.assertRaises(ValueError):
            request_render.render_request(context)

    def test_empty_placeholder_raises_value_error(self):
        context = full_context()
        context["constraints"] = "   "
        with self.assertRaises(ValueError):
            request_render.render_request(context)

    def test_value_containing_todo_raises_value_error(self):
        context = full_context()
        context["required_change"] = "TODO fill this in"
        with self.assertRaises(ValueError):
            request_render.render_request(context)

    def test_value_containing_todo_lowercase_brackets_raises_value_error(self):
        context = full_context()
        context["prerequisites"] = "see <todo> ticket"
        with self.assertRaises(ValueError):
            request_render.render_request(context)

    def test_leftover_angle_bracket_placeholder_raises_value_error(self):
        context = full_context()
        context["title"] = "Fix <df-project-name> onboarding"
        with self.assertRaises(ValueError):
            request_render.render_request(context)

    def test_leftover_angle_bracket_in_base_commit_raises(self):
        context = full_context()
        context["base_commit"] = "<base-commit-hash>"
        with self.assertRaises(ValueError):
            request_render.render_request(context)

    def test_over_char_limit_raises_value_error(self):
        context = full_context()
        context["required_change"] = "x" * request_render.REQUEST_CHAR_LIMIT
        with self.assertRaises(ValueError) as caught:
            request_render.render_request(context)
        self.assertIn("limit", str(caught.exception))

    def test_char_limit_constant_matches_spec(self):
        self.assertEqual(request_render.REQUEST_CHAR_LIMIT, 20000)

    def test_template_has_all_sections(self):
        for label in (
            "Campaign:",
            "Backlog item:",
            "Title:",
            "Base commit:",
            "Prerequisites:",
            "Goal:",
            "Current contracts:",
            "Required change:",
            "Acceptance:",
            "Allowed paths:",
            "Constraints:",
            "Evidence expected:",
        ):
            self.assertIn(label, request_render.REQUEST_TEMPLATE)

    def test_dry_run_adapter_fixture_labelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = cli_adapter.DevFoundryAdapter("http://example.invalid", adapter_mode="dry_run")
            request_path = f"{tmp}/request.txt"
            result = adapter.submit(
                title="Add journal index rebuild",
                project="df-project",
                repo="df-repo",
                base="main",
                request_path=request_path,
            )
            self.assertEqual(result.label, "fixture")


if __name__ == "__main__":
    unittest.main()
