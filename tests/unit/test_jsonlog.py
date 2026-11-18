"""T066 unit tests for structured redacted logging: one JSON object per line."""

from __future__ import annotations

import io
import json
import unittest
from datetime import datetime, timezone

from opsledger.core.clock import FixedClock
from opsledger.http.jsonlog import (
    JsonLogger,
    build_request_record,
    is_sensitive_key,
    redact_value,
)

CLOCK_INSTANT = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)


def _clock() -> FixedClock:
    return FixedClock(datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc))


class JsonLogTests(unittest.TestCase):
    def test_is_sensitive_key_matches_stems_case_insensitively(self) -> None:
        self.assertTrue(is_sensitive_key("password"))
        self.assertTrue(is_sensitive_key("PASSWORD"))
        self.assertTrue(is_sensitive_key("Session-Token"))
        self.assertTrue(is_sensitive_key("session_id"))
        self.assertTrue(is_sensitive_key("cookies"))
        self.assertTrue(is_sensitive_key("auth_token"))
        self.assertTrue(is_sensitive_key("token_count"))
        self.assertFalse(is_sensitive_key("api_key"))
        self.assertFalse(is_sensitive_key("status"))
        self.assertFalse(is_sensitive_key("path"))
        self.assertFalse(is_sensitive_key("request_id"))
        self.assertFalse(is_sensitive_key(None))
        self.assertFalse(is_sensitive_key(7))

    def test_redact_value_redacts_nested_sensitive_keys_without_mutation(self) -> None:
        payload = {
            "name": "x",
            "login": {"password": "hunter2", "keep": 1},
            "items": [{"session_id": "s3", "n": 2}],
            "tuple": ("a",),
        }
        result = redact_value(payload)
        self.assertEqual(result["login"]["password"], "[REDACTED]")
        self.assertEqual(result["login"]["keep"], 1)
        self.assertEqual(result["items"][0]["session_id"], "[REDACTED]")
        self.assertEqual(result["items"][0]["n"], 2)
        self.assertEqual(result["tuple"], ["a"])
        self.assertEqual(payload["login"]["password"], "hunter2")
        self.assertNotIn("hunter2", json.dumps(result))

    def test_build_request_record_has_exact_base_keys_and_strips_query(self) -> None:
        record = build_request_record(
            "rid-1", "GET", "/x?password=hunter2", 404, ts="2026-11-18T12:00:00Z"
        )
        self.assertEqual(
            set(record), {"event", "request_id", "method", "path", "status", "ts"}
        )
        self.assertEqual(record["event"], "request")
        self.assertEqual(record["path"], "/x")
        self.assertNotIn("hunter2", json.dumps(record))

    def test_build_request_record_merges_redacted_fields_without_overriding_base_keys(
        self,
    ) -> None:
        record = build_request_record(
            "rid-2",
            "POST",
            "/y",
            200,
            ts="2026-11-18T12:00:00Z",
            fields={"org": "o1", "password": "hunter2", "request_id": "evil"},
        )
        self.assertEqual(record["org"], "o1")
        self.assertEqual(record["password"], "[REDACTED]")
        self.assertEqual(record["request_id"], "rid-2")

    def test_logger_writes_one_sorted_json_line_per_record(self) -> None:
        stream = io.StringIO()
        logger = JsonLogger(stream=stream)
        logger.log_request("rid-3", "GET", "/z", 200, clock=_clock())
        written = stream.getvalue()
        self.assertTrue(written.endswith("\n"))
        self.assertEqual(written.count("\n"), 1)
        line = json.loads(written)
        self.assertEqual(list(line), ["event", "method", "path", "request_id", "status", "ts"])
        self.assertEqual(line["ts"], "2026-11-18T12:00:00Z")

    def test_logger_log_redacts_raw_records_leaking_sensitive_values(self) -> None:
        stream = io.StringIO()
        logger = JsonLogger(stream=stream)
        logger.log(
            {"request_id": "rid-4", "password": "hunter2", "nested": {"session_token": "abc"}}
        )
        line = json.loads(stream.getvalue())
        self.assertEqual(line["password"], "[REDACTED]")
        self.assertEqual(line["nested"]["session_token"], "[REDACTED]")
        self.assertNotIn("hunter2", json.dumps(line))
        self.assertNotIn("abc", json.dumps(line))


if __name__ == "__main__":
    unittest.main()
