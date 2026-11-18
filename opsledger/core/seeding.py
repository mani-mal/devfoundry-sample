"""T069 bounded restartable synthetic scale seeding core for OpsLedger.

Deterministic rows from a fixed seed, written in bounded batches, described
by a versioned manifest with logical checksums.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from itertools import accumulate
from typing import Any

from .db import transaction

__all__ = [
    "PROFILES",
    "SEED_TABLES",
    "DEFAULT_SEED",
    "DEFAULT_BATCH_SIZE",
    "movement_plan",
    "draw_ids",
    "plan_rows",
    "seed_profile",
    "logical_checksum",
    "build_manifest",
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


def _ts(seconds: int) -> str:
    """Fixed RFC3339 Z text from the base seeding time plus ``seconds``.

    Never the wall clock: fixed RFC3339 Z text keeps seed rows reproducible.
    """
    moment = datetime(2026, 11, 18, 12, 0, 0) + timedelta(seconds=seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def plan_rows(ids: dict[str, list[str]]) -> list[tuple[str, str, tuple, ...]]:
    """Build the full ``(table, sql, params)`` insert plan from an id set.

    Row order is section order and, within a table, per-org block order;
    per-org counts come from :func:`_split` of each profile total.
    """
    orgs = ids["organizations"]
    org_count = len(orgs)
    users = ids["users"]
    sites = ids["sites"]
    assets = ids["assets"]
    work_orders = ids["work_orders"]
    parts = ids["parts"]
    locs = ids["stock_locations"]
    movements = ids["stock_movements"]

    org_counts = _split(len(ids["organizations"]), org_count)
    site_counts = _split(len(sites), org_count)
    asset_counts = _split(len(assets), org_count)
    wo_counts = _split(len(work_orders), org_count)
    mov_counts = _split(len(movements), org_count)

    site_starts = [0, *accumulate(site_counts)]
    asset_starts = [0, *accumulate(asset_counts)]

    wo_starts = [0, *accumulate(wo_counts)]
    mov_starts = [0, *accumulate(mov_counts)]

    rows: list[tuple[str, str, tuple, ...]] = []
    for index, org in enumerate(orgs):
        rows.append((
            "organizations",
            "INSERT OR IGNORE INTO organizations (id, slug, name, created_at) VALUES (?,?,?,?)",
            (org, org[4:], f"Org {index}", _ts(0)),
        ))
    for site_index, site in enumerate(sites):
        block = max(index for index in range(org_count) if site_index >= site_starts[index])
        rows.append((
            "sites",
            "INSERT OR IGNORE INTO sites (id, organization_id, code, name, timezone, created_at) VALUES (?,?,?,?,?,?)",
            (site, orgs[block], f"s{site_index}", f"Site {site_index}", "UTC", _ts(1)),
        ))
    for index, (user, org) in enumerate(zip(users, orgs)):
        rows.append((
            "users",
            "INSERT OR IGNORE INTO users (id, email, display_name, created_at) VALUES (?,?,?,?)",
            (user, f"user{index}@example.test", f"User {index}", _ts(2)),
        ))
        rows.append((
            "memberships",
            "INSERT OR IGNORE INTO memberships (organization_id, user_id, role, created_at) VALUES (?,?,?,?)",
            (org, user, "developer", _ts(2)),
        ))
    for asset_index, asset in enumerate(assets):
        block = max(index for index in range(org_count) if asset_index >= asset_starts[index])
        offset = asset_index - asset_starts[block]
        site_index = site_starts[block] + offset % site_counts[block]
        rows.append((
            "assets",
            "INSERT OR IGNORE INTO assets (id, organization_id, site_id, tag, name, criticality,"
            " purchase_cost_cents, version, created_at, updated_at) VALUES (?,?,?,?,?,?,?,1,?,?)",
            (asset, orgs[block], sites[site_index], f"tag-{asset_index:06d}", f"Asset {asset_index}",
             ("low", "medium", "high")[asset_index % 3], 1000 + asset_index, _ts(3), _ts(3)),
        ))
    for number, wo in enumerate(work_orders):
        block = max(index for index in range(org_count) if number >= wo_starts[index])
        offset = number - wo_starts[block]
        site_index = site_starts[block] + offset % site_counts[block]
        asset_index = asset_starts[block] + offset % asset_counts[block]
        rows.append((
            "work_orders",
            "INSERT OR IGNORE INTO work_orders (id, organization_id, site_id, asset_id, number,"
            " title, description, priority, status, requester_id, version, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wo, orgs[block], sites[site_index], assets[asset_index], f"WO-{number:06d}",
             f"WO {number}", "seed", ("low", "medium", "high")[number % 3],
             ("open", "assigned", "in_progress", "completed")[number % 4], users[block], 1,
             _ts(4), _ts(4)),
        ))
    for index, (part, org, loc) in enumerate(zip(parts, orgs, locs)):
        rows.append((
            "parts",
            "INSERT OR IGNORE INTO parts (id, organization_id, sku, name, unit_of_measure,"
            " standard_cost_cents, version, created_at, updated_at) VALUES (?,?,?,?,?,500,1,?,?)",
            (part, org, f"sku-{index}", f"Part {index}", "unit", _ts(5), _ts(5)),
        ))
        rows.append((
            "stock_locations",
            "INSERT OR IGNORE INTO stock_locations (id, organization_id, code, name, version,"
            " created_at, updated_at) VALUES (?,?,?,?,1,?,?)",
            (loc, org, f"loc-{index}", f"Loc {index}", _ts(5), _ts(5)),
        ))
    for mov_index, mov in enumerate(movements):
        block = max(index for index in range(org_count) if mov_index >= mov_starts[index])
        k = mov_index - mov_starts[block]
        operation, on_hand_delta, reserved_delta = movement_plan(k)
        wo_id = work_orders[wo_starts[block] + k % wo_counts[block]] if operation == "consume" else None
        rows.append((
            "stock_movements",
            "INSERT OR IGNORE INTO stock_movements (id, organization_id, part_id,"
            " stock_location_id, operation, on_hand_delta, reserved_delta, reason,"
            " work_order_id, actor_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (mov, orgs[block], parts[block], locs[block], operation, on_hand_delta, reserved_delta,
             "seed", wo_id, users[block], _ts(6 + mov_index % 1000)),
        ))
    for index, (bal, org) in enumerate(zip(ids["stock_balances"], orgs)):
        org_movs = mov_counts[index]
        on_hand = sum(movement_plan(k)[1] for k in range(org_movs))
        reserved = sum(movement_plan(k)[2] for k in range(org_movs))
        rows.append((
            "stock_balances",
            "INSERT OR IGNORE INTO stock_balances (id, organization_id, part_id,"
            " stock_location_id, on_hand, reserved, version, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (bal, org, parts[index], locs[index], on_hand, reserved, 1, _ts(6), _ts(6)),
        ))
    return rows


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


def seed_profile(conn, *, profile: str = "tiny", seed: int = DEFAULT_SEED,
                 batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Write the drawn plan in bounded restartable batches; return row count.

    Unknown profiles raise :class:`ValueError`; ``batch_size`` must be at
    least 1. Each chunk runs inside one transaction with ``INSERT OR IGNORE``
    per row, so a partially seeded database resumes cleanly.
    """
    if profile not in PROFILES:
        raise ValueError(UNKNOWN_PROFILE_MESSAGE)
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    rows = plan_rows(draw_ids(profile, seed))
    for start in range(0, len(rows), batch_size):
        with transaction(conn) as tx:
            for _, sql, params in rows[start:start + batch_size]:
                tx.execute(sql, params)
    return len(rows)


def logical_checksum(conn) -> str:
    """Sha256 hex over ``SEED_TABLES`` in order, rows as compact JSON.

    The ``salt`` and ``hash`` columns are excluded: nondeterministic
    credential material stays out of fixture checksums per spec §15.
    """
    digest = hashlib.sha256()
    for table in SEED_TABLES:
        columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
        if "salt" in columns:
            columns.remove("salt")
        if "hash" in columns:
            columns.remove("hash")
        selected = ", ".join(columns)
        if table == "memberships":
            rows = conn.execute(
                f"SELECT {selected} FROM {table} ORDER BY organization_id, user_id"
            )
        else:
            rows = conn.execute(f"SELECT {selected} FROM {table} ORDER BY id")
        for row in rows:
            digest.update(json.dumps(list(row), sort_keys=True, separators=(",", ":")).encode())
            digest.update(b"\n")
    return digest.hexdigest()


def build_manifest(conn, *, profile: str, seed: int, batch_size: int) -> dict:
    """Versioned manifest of counts and the logical checksum for the seed."""
    return {
        "manifest_version": 1,
        "profile": profile,
        "seed": seed,
        "batch_size": batch_size,
        "counts": {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                   for table in SEED_TABLES},
        "logical_checksum": logical_checksum(conn),
    }
