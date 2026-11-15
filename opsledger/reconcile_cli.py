"""Reconciliation CLI for OpsLedger (T040, M5).

Stdlib argparse only. Runnable via ``python -m opsledger.reconcile_cli``.
Reports, for one part/location, the persisted balances against the
movement-sum recomputation (:func:`opsledger.inventory.reconcile_balance`)
using an independent connection; exits 0 when they agree and 1 when they
do not. Application errors surface only the public message on stderr --
never a traceback and never a path (neither the database path nor the
migrations directory are printed).

- ``reconcile DATABASE --part PART_ID --location LOCATION_ID``: print one
  JSON object with the balance, the movement sums, and ``matches``.
"""

from __future__ import annotations

import argparse
import json
import sys

from opsledger.core.db import connect
from opsledger.core.errors import ApplicationError
from opsledger.inventory import reconcile_balance

__all__ = [
    "main",
]


def _resolve_context(conn, part_id):
    """Return the part's organization context, or None when absent.

    The CLI is a local diagnostics adapter: it resolves the part's own
    organization and reconciles inside it. This is a plain lookup, not a
    business rule.
    """
    row = conn.execute(
        "SELECT organization_id FROM parts WHERE id = ?", (part_id,)
    ).fetchone()
    if row is None:
        return None
    from opsledger.core.context import OrganizationContext

    return OrganizationContext(organization_id=row["organization_id"], actor_id=None)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opsledger-reconcile",
        description="Reconcile persisted balances against the stock movement sum.",
    )
    parser.add_argument("database", help="path to the SQLite database file")
    parser.add_argument("--part", required=True, help="part id to reconcile")
    parser.add_argument(
        "--location", required=True, help="stock location id to reconcile"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    from opsledger.core.clock import RealClock

    ns = _build_parser().parse_args(argv)
    clock = RealClock()
    conn = connect(ns.database)
    try:
        context = _resolve_context(conn, ns.part)
        if context is None:
            print("part not found", file=sys.stderr)
            return 1
        report = reconcile_balance(
            conn, context, part_id=ns.part, location_id=ns.location, clock=clock
        )
    except ApplicationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(
        json.dumps(
            {
                "balance": dict(report["balance"]),
                "on_hand_sum": report["on_hand_sum"],
                "reserved_sum": report["reserved_sum"],
                "matches": report["matches"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
