"""T069 bounded restartable synthetic scale seeding core for OpsLedger.

Deterministic rows from a fixed seed, written in bounded batches, described
by a versioned manifest with logical checksums.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import transaction

__all__ = [
    "PROFILES",
    "SEED_TABLES",
    "DEFAULT_SEED",
    "DEFAULT_BATCH_SIZE",
    "movement_plan",
    "draw_ids",
]

PROFILES: dict[str, dict[str, int]] = {
    "tiny": {
        "organizations": 2, "sites_total": 4, "assets": 20,
        "work_orders": 40, "stock_movements": 100,
    },
    "medium": {
        "organizations": 3, "sites_total": 15, "assets": 5000,
        "work_orders": 25000, "stock_movements": 100000,
    },
    "large": {
        "organizations": 5, "sites_total": 50, "assets": 25000,
        "work_orders": 100000, "stock_movements": 500000,
    },
}

SEED_TABLES = (
    "organizations", "sites", "users", "memberships", "assets",
    "work_orders", "parts", "stock_locations", "stock_balances",
    "stock_movements",
)

DEFAULT_SEED = 20261118
DEFAULT_BATCH_SIZE = 64

UNKNOWN_PROFILE_MESSAGE = "unknown seeding profile: use one of " + ", ".join(sorted(PROFILES))


def _split(total: int, parts: int) -> list[int]:
    """Deterministic remainder split of ``total`` rows over ``parts``.

    The first ``total % parts`` parts receive one extra row.
    """
    base, extra = divmod(total, parts)
    return [base + 1 if index < extra else base for index in range(parts)]


def movement_plan(index_in_org: int) -> tuple[str, int, int]:
    """Return the fixed ledger pattern entry at ``index_in_org``.

    Position 0 is a full receive; every 10th position (after position 0) is
    a smaller receive; odd positions reserve; even others consume. The
    replay of any prefix never goes negative.
    """
    if index_in_org == 0:
        return ("receive", 50, 0)
    if index_in_org % 10 == 0:
        return ("receive", 30, 0)
    if index_in_org % 2 == 1:
        return ("reserve", 0, 3)
    return ("consume", -3, -3)


def draw_ids(profile: str, seed: int) -> dict[str, list[str]]:
    """Draw the deterministic id set for ``profile`` from ``seed``.

    Creates one :class:`random.Random` and draws in a fixed order; the
    order is load-bearing for part 2's determinism.
    """
    if profile not in PROFILES:
        raise ValueError(UNKNOWN_PROFILE_MESSAGE)
    counts = PROFILES[profile]
    org_count = counts["organizations"]
    rng = random.Random(seed)

    def ident(prefix: str) -> str:
        return f"{prefix}-{rng.getrandbits(128):032x}"

    return {
        "organizations": [ident("org") for _ in range(org_count)],
        "users": [ident("usr") for _ in range(org_count)],
        "sites": [ident("site") for _ in range(counts["sites_total"])],
        "assets": [ident("ast") for _ in range(counts["assets"])],
        "work_orders": [ident("wo") for _ in range(counts["work_orders"])],
        "parts": [ident("prt") for _ in range(org_count)],
        "stock_locations": [ident("stl") for _ in range(org_count)],
        "stock_balances": [ident("bal") for _ in range(org_count)],
        "stock_movements": [ident("mov") for _ in range(counts["stock_movements"])],
    }


# Part 2 (T069 follow-up): plan_rows, seed_profile, logical_checksum, build_manifest.
