"""T066 structured redacted logging core: one JSON object per line.

Redacted by default and correlated by request id.
"""

from __future__ import annotations

import json
import sys
from typing import Any

__all__ = [
    "SENSITIVE_STEMS",
    "REDACTED_TEXT",
    "JsonLogger",
    "build_request_record",
    "is_sensitive_key",
    "redact_value",
]

SENSITIVE_STEMS = ("password", "session", "cookie", "authorization", "token", "secret")
REDACTED_TEXT = "[REDACTED]"


def is_sensitive_key(key: object) -> bool:
    """Return True only when key is a str containing a sensitive stem."""
    return isinstance(key, str) and any(stem in key.lower() for stem in SENSITIVE_STEMS)


def redact_value(value: Any) -> Any:
    """Return a redacted copy of value, recursively, without mutating it."""
    if isinstance(value, dict):
        return {
            key: REDACTED_TEXT
            if is_sensitive_key(key)
            else redact_value(inner)
            for key, inner in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    return value


def build_request_record(
    request_id: str,
    method: str,
    path: str,
    status: int,
    *,
    ts: str,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one request log record (this shape, nothing more)."""
    record: dict[str, Any] = {
        "event": "request",
        "request_id": request_id,
        "method": method,
        "path": path.split("?", 1)[0],
        "status": status,
        "ts": ts,
    }
    if fields:
        for key, value in redact_value(fields).items():
            if key not in record:
                record[key] = value
    return record


class JsonLogger:
    """Emit one redacted JSON object per line to a text stream."""

    def __init__(self, *, stream: Any = None) -> None:
        self._stream = stream

    def _resolve_stream(self) -> Any:
        return self._stream if self._stream is not None else sys.stderr

    def log(self, record: dict[str, Any]) -> None:
        """Write one redacted JSON line, then flush the stream."""
        stream = self._resolve_stream()
        line = json.dumps(
            redact_value(record), sort_keys=True, separators=(",", ":")
        )
        stream.write(line + "\n")
        stream.flush()

    def log_request(
        self,
        request_id: str,
        method: str,
        path: str,
        status: int,
        *,
        clock: Any,
        fields: dict[str, Any] | None = None,
    ) -> None:
        """Log one HTTP request with a clock-derived timestamp."""
        self.log(
            build_request_record(
                request_id, method, path, status, ts=clock.timestamp(), fields=fields
            )
        )
