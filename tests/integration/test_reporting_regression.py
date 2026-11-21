import csv
import io
import os
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.audit.events import record_event
from opsledger.audit.queries import count_events, query_events
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.migrations import migrate
from opsledger.inventory import adjust_stock, consume_reservation, reserve_stock
from opsledger.parts import create_part, create_stock_location
from opsledger.purchasing.lifecycle import approve_purchase_request, submit_purchase_request
from opsledger.purchasing.orders import issue_order
from opsledger.purchasing.receipts import receive_order
from opsledger.purchasing.requests import create_purchase_request
from opsledger.purchasing.vendors import create_vendor
from opsledger.reporting.cost_report import asset_cost_report
from opsledger.reporting.csv_export import CSV_HEADER, export_work_orders
from opsledger.reporting.dashboard import dashboard
from opsledger.workorders import create_work_order, record_labor
from opsledger.workorders.transitions import transition_work_order


def _seed_identities(conn):
    conn.execute("INSERT OR IGNORE INTO organizations (id, slug, name, created_at) VALUES ('org-aaa', 'aaa', 'Org aaa', '2026-11-01T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO organizations (id, slug, name, created_at) VALUES ('org-bbb', 'bbb', 'Org bbb', '2026-11-01T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO users (id, email, display_name, created_at) VALUES ('user-111', 'u1@example.test', 'User 111', '2026-11-01T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO users (id, email, display_name, created_at) VALUES ('user-222', 'u2@example.test', 'User 222', '2026-11-01T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO memberships (organization_id, user_id, role, created_at) VALUES ('org-aaa', 'user-222', 'approver', '2026-11-01T00:00:00Z')")
    conn.commit()


@dataclass(frozen=True)
class ReportingContext(OrganizationContext):
    role: str = "admin"


def _tick_factory():
    base = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
    counter = [0]

    def tick():
        counter[0] += 1
        return FixedClock(base + timedelta(seconds=counter[0]))

    return tick


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    unittest.addModuleCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
    conn = connect(tmp.name)
    unittest.addModuleCleanup(lambda c=conn: c.close())
    migrate(conn, "opsledger/migrations")
    _seed_identities(conn)
    return conn


def _build_fixture(conn, tick, include_purchasing=True):
    """Build the combined M8 fixture; returns the ids it created (machine-verified)."""
    ctx = OrganizationContext(organization_id="org-aaa", actor_id="user-111")
    site = create_site(conn, ctx, code="site-1", name="Site 1", clock=tick())
    a1 = create_asset(conn, ctx, site_id=site["id"], tag="pump-001", name="Pump 001", criticality="high", purchase_cost_cents=500000, clock=tick())
    a2 = create_asset(conn, ctx, site_id=site["id"], tag="pump-002", name="Pump 002", criticality="low", purchase_cost_cents=100000, clock=tick())
    wo1 = create_work_order(conn, ctx, site_id=site["id"], asset_id=a1["id"], number="WO-0001", title="Fix pump 1", description="", priority="high", requester_id="user-111", clock=tick())
    wo2 = create_work_order(conn, ctx, site_id=site["id"], asset_id=a1["id"], number="WO-0002", title="Fix pump 2", description="", priority="medium", requester_id="user-111", clock=tick())
    wo3 = create_work_order(conn, ctx, site_id=site["id"], asset_id=a2["id"], number="WO-0003", title="Check pump 3", description="", priority="low", requester_id="user-111", clock=tick())
    transition_work_order(conn, ctx, work_order_id=wo2["id"], to_status="assigned", expected_version=1, reason="assign", actor_id="user-111", clock=tick())
    transition_work_order(conn, ctx, work_order_id=wo2["id"], to_status="in_progress", expected_version=2, reason="start", actor_id="user-111", clock=tick())
    transition_work_order(conn, ctx, work_order_id=wo2["id"], to_status="completed", expected_version=3, reason="done", actor_id="user-111", clock=tick())
    transition_work_order(conn, ctx, work_order_id=wo3["id"], to_status="cancelled", expected_version=1, reason="not needed", actor_id="user-111", clock=tick())
    part = create_part(conn, ctx, sku="bolt-m8", name="Bolt M8", unit_of_measure="unit", standard_cost_cents=250, clock=tick())
    loc = create_stock_location(conn, ctx, code="sto-1", name="Store 1", clock=tick())
    adjust_stock(conn, ctx, part_id=part["id"], location_id=loc["id"], quantity_delta=50, reason="initial stock", expected_version=1, actor_id="user-111", clock=tick())
    res = reserve_stock(conn, ctx, part_id=part["id"], location_id=loc["id"], work_order_id=wo1["id"], quantity=10, expected_version=2, actor_id="user-111", clock=tick())
    consume_reservation(conn, ctx, reservation_id=res["id"], quantity=10, expected_version=3, actor_id="user-111", clock=tick())
    record_labor(conn, ctx, work_order_id=wo1["id"], technician_id="user-111", minutes=90, rate_cents_per_hour=8000, clock=tick())
    record_labor(conn, ctx, work_order_id=wo2["id"], technician_id="user-111", minutes=100, rate_cents_per_hour=8000, clock=tick())
    record_event(conn, ctx, entity_type="site", entity_id=site["id"], operation="site.created", details={"code": "site-1"}, clock=tick())
    result = {"site": site, "a1": a1, "a2": a2, "wo1": wo1, "wo2": wo2, "wo3": wo3, "part": part, "loc": loc}
    if include_purchasing:
        vendor = create_vendor(conn, ctx, name="Acme", contact_email=None, clock=tick())
        prq = create_purchase_request(conn, ctx, vendor_id=vendor["id"], lines=[{"part_id": part["id"], "quantity": 10, "unit_cost_cents": 300}], clock=tick())
        submit_purchase_request(conn, ctx, purchase_request_id=prq["id"], expected_version=1, clock=tick())
        approver_ctx = ReportingContext(organization_id="org-aaa", actor_id="user-222", role="approver")
        approve_purchase_request(conn, approver_ctx, purchase_request_id=prq["id"], expected_version=2, clock=tick(), reason="ok")
        order, _record, _replayed = issue_order(conn, ctx, purchase_request_id=prq["id"], expected_version=3, actor_id="user-111", clock=tick(), idempotency_key="issue-m8")
        receipt, _record2, _replayed2 = receive_order(conn, ctx, purchase_order_id=order["id"], stock_location_id=loc["id"], lines=[{"part_id": part["id"], "quantity": 6}], expected_version=order["version"], actor_id="user-111", clock=tick(), idempotency_key="rcpt-m8")
        result.update({"vendor": vendor, "prq": prq, "order": order, "receipt": receipt})
    return result


class ReportingRegressionTests(unittest.TestCase):
    def test_dashboard_reconciles_with_independent_sql_counts(self):
        conn = _fresh_db()
        _build_fixture(conn, _tick_factory())
        admin = ReportingContext(organization_id="org-aaa", actor_id="user-111", role="admin")
        ctx = OrganizationContext(organization_id="org-aaa", actor_id="user-111")
        d = dashboard(conn, ctx, actor=admin)
        wo = d["work_orders"]
        self.assertEqual(3, wo["total"])
        self.assertEqual(1, wo["by_status"]["open"])
        self.assertEqual(1, wo["by_status"]["completed"])
        self.assertEqual(1, wo["by_status"]["cancelled"])
        self.assertEqual(0, wo["by_status"]["assigned"])
        self.assertEqual(0, wo["by_status"]["in_progress"])
        self.assertEqual(0, wo["by_status"]["blocked"])
        self.assertEqual(0, wo["by_status"]["closed"])
        self.assertEqual(2, d["assets"]["total"])
        self.assertEqual(46, d["stock"]["on_hand"])
        self.assertEqual(0, d["stock"]["reserved"])
        self.assertEqual(25333, d["labor_cost_cents"])
        direct_total = conn.execute("SELECT COUNT(*) AS c FROM work_orders WHERE organization_id = 'org-aaa'").fetchone()["c"]
        direct_labor = conn.execute("SELECT COALESCE(SUM(cost_cents), 0) AS s FROM labor_entries WHERE organization_id = 'org-aaa'").fetchone()["s"]
        direct_assets = conn.execute("SELECT COUNT(*) AS c FROM assets WHERE organization_id = 'org-aaa' AND archived_at IS NULL").fetchone()["c"]
        self.assertEqual(direct_total, wo["total"])
        self.assertEqual(direct_labor, d["labor_cost_cents"])
        self.assertEqual(direct_assets, d["assets"]["total"])

    def test_cost_report_reconciles_with_ledger(self):
        conn = _fresh_db()
        _build_fixture(conn, _tick_factory())
        admin = ReportingContext(organization_id="org-aaa", actor_id="user-111", role="admin")
        ctx = OrganizationContext(organization_id="org-aaa", actor_id="user-111")
        rows = {row["tag"]: row for row in asset_cost_report(conn, ctx, actor=admin)}
        self.assertEqual(25333, rows["pump-001"]["labor_cost_cents"])
        self.assertEqual(2500, rows["pump-001"]["consumed_part_cost_cents"])
        self.assertEqual(27833, rows["pump-001"]["total_cost_cents"])
        self.assertEqual((0, 0, 0), (rows["pump-002"]["labor_cost_cents"], rows["pump-002"]["consumed_part_cost_cents"], rows["pump-002"]["total_cost_cents"]))
        direct_labor = conn.execute("SELECT COALESCE(SUM(cost_cents), 0) AS s FROM labor_entries WHERE organization_id = 'org-aaa'").fetchone()["s"]
        direct_consumed = conn.execute(
            "SELECT COALESCE(SUM(sm.on_hand_delta * -1 * p.standard_cost_cents), 0) AS s"
            " FROM stock_movements sm JOIN parts p ON p.id = sm.part_id"
            " WHERE sm.organization_id = 'org-aaa' AND sm.operation = 'consume'"
        ).fetchone()["s"]
        self.assertEqual(direct_labor, rows["pump-001"]["labor_cost_cents"])
        self.assertEqual(direct_consumed, rows["pump-001"]["consumed_part_cost_cents"])

    def test_csv_export_round_trips_and_reconciles(self):
        conn = _fresh_db()
        _build_fixture(conn, _tick_factory())
        auditor = ReportingContext(organization_id="org-aaa", actor_id="user-111", role="auditor")
        ctx = OrganizationContext(organization_id="org-aaa", actor_id="user-111")
        text = export_work_orders(conn, ctx, actor=auditor)
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(4, len(rows))
        self.assertEqual(CSV_HEADER, rows[0])
        self.assertEqual(["WO-0001", "WO-0002", "WO-0003"], [r[1] for r in rows[1:]])
        statuses = [r[3] for r in rows[1:]]
        self.assertEqual(1, statuses.count("open"))
        self.assertEqual(1, statuses.count("completed"))
        self.assertEqual(1, statuses.count("cancelled"))

    def test_audit_queries_reconcile_with_recorded_history(self):
        conn = _fresh_db()
        _build_fixture(conn, _tick_factory())
        admin = ReportingContext(organization_id="org-aaa", actor_id="user-111", role="admin")
        ctx = OrganizationContext(organization_id="org-aaa", actor_id="user-111")
        direct = conn.execute("SELECT COUNT(*) AS c FROM audit_events WHERE organization_id = 'org-aaa'").fetchone()["c"]
        self.assertEqual(9, direct)
        self.assertEqual(direct, count_events(conn, ctx, actor=admin))
        self.assertEqual(1, count_events(conn, ctx, actor=admin, operation="site.created"))
        site_rows = query_events(conn, ctx, actor=admin, entity_type="site")
        self.assertEqual(1, len(site_rows))
        self.assertEqual("site.created", site_rows[0]["operation"])

    def test_dashboard_before_and_after_the_receipt(self):
        ctx = OrganizationContext(organization_id="org-aaa", actor_id="user-111")
        admin = ReportingContext(organization_id="org-aaa", actor_id="user-111", role="admin")
        conn1 = _fresh_db()
        _build_fixture(conn1, _tick_factory(), include_purchasing=False)
        d1 = dashboard(conn1, ctx, actor=admin)
        self.assertEqual(40, d1["stock"]["on_hand"])
        self.assertEqual(25333, d1["labor_cost_cents"])
        self.assertEqual(2, d1["assets"]["total"])
        conn2 = _fresh_db()
        fx2 = _build_fixture(conn2, _tick_factory(), include_purchasing=True)
        d2 = dashboard(conn2, ctx, actor=admin)
        self.assertEqual(46, d2["stock"]["on_hand"])
        self.assertEqual(25333, d2["labor_cost_cents"])
        self.assertEqual(2, d2["assets"]["total"])
        receipt_line = conn2.execute(
            "SELECT unit_cost_cents, quantity FROM receipt_lines WHERE receipt_id = ?",
            (fx2["receipt"]["id"],),
        ).fetchone()
        self.assertEqual(250, receipt_line["unit_cost_cents"])
        self.assertEqual(6, receipt_line["quantity"])

    def test_org_scoping_holds_across_all_four_modules(self):
        conn = _fresh_db()
        _build_fixture(conn, _tick_factory())
        tick = _tick_factory()
        ctx_a = OrganizationContext(organization_id="org-aaa", actor_id="user-111")
        ctx_b = OrganizationContext(organization_id="org-bbb", actor_id="user-111")
        admin_a = ReportingContext(organization_id="org-aaa", actor_id="user-111", role="admin")
        bbb_site = create_site(conn, ctx_b, code="site-bbb", name="B", clock=tick())
        bbb_asset = create_asset(conn, ctx_b, site_id=bbb_site["id"], tag="bbb-pump", name="B pump", criticality="low", purchase_cost_cents=1, clock=tick())
        create_work_order(conn, ctx_b, site_id=bbb_site["id"], asset_id=bbb_asset["id"], number="WO-BBB-1", title="B work", description="", priority="low", requester_id="user-111", clock=tick())
        record_event(conn, ctx_b, entity_type="site", entity_id=bbb_site["id"], operation="site.created", details={"code": "site-bbb"}, clock=tick())
        d_a = dashboard(conn, ctx_a, actor=admin_a)
        self.assertEqual(3, d_a["work_orders"]["total"])
        self.assertEqual(2, d_a["assets"]["total"])
        d_b = dashboard(conn, ctx_b, actor=admin_a)
        self.assertEqual(1, d_b["work_orders"]["total"])
        self.assertEqual(1, d_b["assets"]["total"])
        rows_a = asset_cost_report(conn, ctx_a, actor=admin_a)
        self.assertEqual(2, len(rows_a))
        self.assertEqual({"pump-001", "pump-002"}, {row["tag"] for row in rows_a})
        auditor_a = ReportingContext(organization_id="org-aaa", actor_id="user-111", role="auditor")
        csv_text = export_work_orders(conn, ctx_a, actor=auditor_a)
        self.assertNotIn("WO-BBB-1", csv_text)
        self.assertNotIn("bbb-pump", csv_text)
        self.assertEqual(9, count_events(conn, ctx_a, actor=admin_a))
        self.assertEqual(1, count_events(conn, ctx_b, actor=admin_a))
