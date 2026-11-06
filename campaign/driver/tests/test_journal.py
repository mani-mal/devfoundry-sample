"""Offline unit tests for the campaign evidence journal."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from campaign.driver import journal


def sample_event(**overrides) -> dict:
    event = {
        "schema_version": 1,
        "campaign_id": "opsledger-run-001",
        "backlog_id": "B02",
        "event": "submit",
        "occurred_at": "2026-11-06T12:00:00Z",
        "task_id": None,
        "attempt_id": None,
        "base_commit": None,
        "request_sha256": None,
        "patch_sha256": None,
        "environment_build": None,
        "pack_digest": None,
        "platform_state": None,
        "campaign_state": None,
        "verdict": None,
        "evidence_paths": [],
    }
    event.update(overrides)
    return event


class TestJournal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.journal_path = self.root / "events.jsonl"

    def test_append_load_round_trip(self):
        event = sample_event(task_id="tsk-abc12345", attempt_id="a1")
        journal.append_event(self.journal_path, event)
        event2 = sample_event(backlog_id="B05", event="submit", occurred_at="2026-11-06T12:01:00Z")
        journal.append_event(self.journal_path, event2)
        loaded = journal.load_events(self.journal_path, warn=lambda _msg: None)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["backlog_id"], "B02")
        self.assertEqual(loaded[0]["task_id"], "tsk-abc12345")
        self.assertEqual(loaded[0]["evidence_paths"], [])
        self.assertEqual(loaded[1]["backlog_id"], "B05")

    def test_partial_final_line_skipped_complete_records_load(self):
        good = json.dumps(sample_event(), sort_keys=True)
        partial = '{"schema_version": 1, "campaign_id": "opsledger-run-001", "backlog_id"'
        self.journal_path.write_text(good + "\n" + partial, encoding="utf-8")
        warnings: list[str] = []
        loaded = journal.load_events(self.journal_path, warn=warnings.append)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["backlog_id"], "B02")
        self.assertTrue(warnings, "a warning must be emitted for the partial line")
        self.assertIn("malformed", warnings[0])

    def test_partial_final_line_warning_goes_to_stderr(self):
        good = json.dumps(sample_event(), sort_keys=True)
        self.journal_path.write_text(good + "\n{broken\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as _unused:
            import io
            import contextlib

            stderr_capture = io.StringIO()
            with contextlib.redirect_stderr(stderr_capture):
                loaded = journal.load_events(self.journal_path)
        self.assertEqual(len(loaded), 1)
        self.assertIn("campaign journal", stderr_capture.getvalue())

    def test_rebuild_index_projection(self):
        events = [
            sample_event(backlog_id="B02", event="submit"),
            sample_event(
                backlog_id="B02",
                event="verdict",
                occurred_at="2026-11-06T12:05:00Z",
                task_id="tsk-abc12345",
                verdict="accepted",
            ),
            sample_event(
                backlog_id="B05",
                event="verdict",
                occurred_at="2026-11-06T12:06:00Z",
                verdict="blocked",
            ),
            sample_event(
                backlog_id="B05",
                event="verdict",
                occurred_at="2026-11-06T12:07:00Z",
                verdict="accepted",
            ),
            sample_event(
                backlog_id="B07",
                event="submit",
                occurred_at="2026-11-06T12:08:00Z",
                verdict=None,
            ),
        ]
        for event in events:
            journal.append_event(self.journal_path, event)
        index_path = self.root / "index.json"
        projection = journal.rebuild_index(self.journal_path, index_path)
        self.assertEqual(projection["schema_version"], 1)
        self.assertEqual(projection["campaign_id"], "opsledger-run-001")
        self.assertEqual(projection["backlog_ids"], ["B02", "B05", "B07"])
        self.assertEqual(projection["task_ids"], ["tsk-abc12345"])
        self.assertEqual(projection["event_count"], 5)
        self.assertEqual(projection["verdicts"], {"B02": "accepted", "B05": "accepted"})
        self.assertRegex(projection["rebuilt_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_rebuild_index_written_atomically_valid_json(self):
        journal.append_event(self.journal_path, sample_event())
        index_path = self.root / "index.json"
        journal.rebuild_index(self.journal_path, index_path)
        self.assertTrue(index_path.exists())
        data = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(data["event_count"], 1)
        leftovers = [p.name for p in self.root.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [], "temporary index file must be replaced away")

    def test_rebuild_index_empty_journal(self):
        index_path = self.root / "index.json"
        projection = journal.rebuild_index(self.root / "missing.jsonl", index_path)
        self.assertIsNone(projection["campaign_id"])
        self.assertEqual(projection["backlog_ids"], [])
        self.assertEqual(projection["event_count"], 0)

    def test_utc_now_format(self):
        self.assertRegex(journal.utc_now(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_event_schema_fields_constant(self):
        self.assertEqual(
            journal.EVENT_SCHEMA_FIELDS,
            [
                "schema_version",
                "campaign_id",
                "backlog_id",
                "event",
                "occurred_at",
                "task_id",
                "attempt_id",
                "base_commit",
                "request_sha256",
                "patch_sha256",
                "environment_build",
                "pack_digest",
                "platform_state",
                "campaign_state",
                "verdict",
                "evidence_paths",
            ],
        )

    def test_default_paths(self):
        self.assertEqual(journal.JOURNAL_PATH, Path("campaign/journal/events.jsonl"))
        self.assertEqual(journal.INDEX_PATH, Path("campaign/journal/index.json"))

    def test_rebuild_index_pattern_check(self):
        journal.append_event(self.journal_path, sample_event())
        index_path = self.root / "index.json"
        projection = journal.rebuild_index(self.journal_path, index_path)
        self.assertTrue(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", projection["rebuilt_at"]))


if __name__ == "__main__":
    unittest.main()
