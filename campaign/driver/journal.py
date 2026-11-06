"""Resumable evidence journal for the DevFoundry campaign.

The journal is an append-only JSONL file of campaign events. It is private
local evidence: never committed, never sent to the server. A partially
written final line (e.g. after a crash mid-append) is skipped on load so a
resume always rebuilds from complete records only.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

EVENT_SCHEMA_FIELDS: list[str] = [
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
]

EVENT_SCHEMA_VERSION = 1

JOURNAL_DIR = Path("campaign") / "journal"
JOURNAL_PATH = JOURNAL_DIR / "events.jsonl"
INDEX_PATH = JOURNAL_DIR / "index.json"


def utc_now() -> str:
    """Canonical UTC RFC3339 timestamp with second precision, ending in Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_event(event: dict) -> dict:
    """Fill defaults for optional fields so records are self-describing."""
    record = dict(event)
    record.setdefault("schema_version", EVENT_SCHEMA_VERSION)
    record.setdefault("task_id", None)
    record.setdefault("attempt_id", None)
    record.setdefault("base_commit", None)
    record.setdefault("request_sha256", None)
    record.setdefault("patch_sha256", None)
    record.setdefault("environment_build", None)
    record.setdefault("pack_digest", None)
    record.setdefault("platform_state", None)
    record.setdefault("campaign_state", None)
    record.setdefault("verdict", None)
    record.setdefault("evidence_paths", [])
    return record


def append_event(journal_path: Path, event: dict) -> None:
    """Append one JSON line to the journal, atomic-enough for resume purposes."""
    record = _normalize_event(event)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    journal_path = Path(journal_path)
    if journal_path.parent and not journal_path.parent.exists():
        journal_path.parent.mkdir(parents=True, exist_ok=True)
    with open(journal_path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_events(journal_path: Path, warn: Callable[[str], None] | None = None) -> list[dict]:
    """Read all COMPLETE JSONL records.

    A malformed or partial final line (crash mid-append) is skipped with a
    warning to stderr so resume always rebuilds from complete records only.
    Malformed non-final lines are also skipped with a warning rather than
    breaking the load.
    """
    journal_path = Path(journal_path)
    if not journal_path.exists():
        return []
    records: list[dict] = []
    with open(journal_path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as error:
            _warn(warn, f"campaign journal: skipping malformed line {number} ({error}); rebuild from complete records")
            continue
        if not isinstance(parsed, dict):
            _warn(warn, f"campaign journal: skipping line {number}: not a JSON object")
            continue
        records.append(parsed)
    return records


def _warn(warn: Callable[[str], None] | None, message: str) -> None:
    target = warn if warn is not None else (lambda text: print(text, file=sys.stderr))
    target(message)


def rebuild_index(journal_path: Path, index_path: Path) -> dict:
    """Write index.json as a projection of complete journal records.

    Returns the projection that was written. Written via temporary file +
    os.replace so readers never observe a half-written index.
    """
    records = load_events(journal_path)
    backlog_ids: set[str] = set()
    task_ids: set[str] = set()
    latest_verdicts: dict[str, str] = {}
    for record in records:
        backlog_id = record.get("backlog_id")
        if backlog_id:
            backlog_ids.add(str(backlog_id))
            verdict = record.get("verdict")
            if verdict:
                latest_verdicts[str(backlog_id)] = str(verdict)
        task_id = record.get("task_id")
        if task_id:
            task_ids.add(str(task_id))
    projection = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "rebuilt_at": utc_now(),
        "campaign_id": records[0].get("campaign_id") if records else None,
        "backlog_ids": sorted(backlog_ids),
        "task_ids": sorted(task_ids),
        "event_count": len(records),
        "verdicts": {key: latest_verdicts[key] for key in sorted(latest_verdicts)},
    }
    index_path = Path(index_path)
    if index_path.parent and not index_path.parent.exists():
        index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = index_path.with_name(index_path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(projection, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, index_path)
    return projection
