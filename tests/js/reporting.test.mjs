import test from "node:test";
import assert from "node:assert/strict";
import { WORK_ORDER_STATUSES, createReportingState, setDashboard, setSearchResults, setAuditEvents, setReportingError, clearReportingError, formatWorkOrderLine, renderDashboard, renderSearchResults, renderAuditEvents } from "../../web/js/reporting.mjs";

function el(tag) {
  return {
    tagName: tag,
    children: [],
    textContent: null,
    attributes: {},
    appendChild(c) {
      this.children.push(c);
      return c;
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
  };
}

function allTexts(node) {
  const out = [];
  if (node.textContent !== null && node.textContent !== undefined) {
    out.push(node.textContent);
  }
  for (const child of node.children || []) {
    out.push(...allTexts(child));
  }
  return out;
}

test("createReportingState returns the empty shape with no storage fields", () => {
  const state = createReportingState();
  assert.deepEqual(state, {
    dashboard: null,
    search: null,
    audit: [],
    viewerId: null,
    error: null,
  });
  assert.equal(Object.hasOwn(state, "localStorage"), false);
  assert.equal(Object.hasOwn(state, "sessionStorage"), false);
});

test("WORK_ORDER_STATUSES lists the seven states in order", () => {
  const expected = [
    "open",
    "assigned",
    "in_progress",
    "blocked",
    "completed",
    "closed",
    "cancelled",
  ];
  assert.equal(WORK_ORDER_STATUSES.length, 7);
  assert.deepEqual(WORK_ORDER_STATUSES, expected);
});

test("setDashboard replaces the layer without mutating the input object", () => {
  const before = createReportingState();
  const snapshot = JSON.stringify(before);
  const payload = { work_orders: { total: 3 } };
  Object.freeze(payload);
  const after = setDashboard(before, payload);
  assert.equal(JSON.stringify(before), snapshot);
  assert.notEqual(before, after);
  assert.equal(after.dashboard, payload);
});

test("formatWorkOrderLine contains the number, the title, and the status", () => {
  const rendered = formatWorkOrderLine({ number: "WO-0001", title: "Fix pump", status: "open" });
  assert.ok(rendered.includes("WO-0001"));
  assert.ok(rendered.includes("Fix pump"));
  assert.ok(rendered.includes("open"));
});

test("renderDashboard with data: by_status LIs before totals, zero statuses omitted", () => {
  globalThis.document = { createElement: (tag) => el(tag) };
  const state = {
    dashboard: {
      work_orders: {
        total: 3,
        by_status: { open: 1, assigned: 0, in_progress: 1, blocked: 0, completed: 1, closed: 0, cancelled: 0 },
      },
      assets: { total: 1 },
      stock: { on_hand: 130, reserved: 5 },
      labor_cost_cents: 34333,
    },
    search: null,
    audit: [],
    viewerId: null,
    error: null,
  };
  const container = el("div");
  renderDashboard(container, state);
  const texts = allTexts(container);
  for (const expected of ["open: 1", "in_progress: 1", "Total work orders: 3", "Assets: 1", "Stock on hand: 130", "Stock reserved: 5", "Labor cost: 34333 cents"]) {
    assert.ok(texts.includes(expected), `missing: ${expected}`);
  }
  assert.ok(!texts.some((t) => t.startsWith("assigned:") || t.startsWith("blocked:") || t.startsWith("closed:") || t.startsWith("cancelled:")));
  assert.equal(allTexts(container)[0], "open: 1");
});

test("renderDashboard error paragraph is an assertive live region", () => {
  const state = setReportingError(createReportingState(), "Dashboard failed to load.");
  const container = el("div");
  globalThis.document = { createElement: (tag) => el(tag) };
  renderDashboard(container, state);
  assert.equal(container.children.length, 1);
  assert.equal(container.children[0].textContent, "Dashboard failed to load.");
  assert.equal(container.children[0].attributes.role, "alert");
  assert.equal(container.children[0].attributes["aria-live"], "assertive");
});

test("renderDashboard with dashboard === null appends P No dashboard loaded yet", () => {
  const container = el("div");
  renderDashboard(container, createReportingState());
  assert.ok(container.children.some((c) => c.tagName === "p" && c.textContent === "No dashboard loaded yet."));
});

test("renderSearchResults with data: LIs for asset and work order", () => {
  const state = {
    dashboard: null,
    search: {
      query: "pump",
      assets: [{ id: "ast-1", tag: "pump-001", name: "Pump One" }],
      work_orders: [{ id: "wor-1", number: "WO-0001", title: "Fix pump", status: "open" }],
      parts: [],
    },
    audit: [],
    viewerId: null,
    error: null,
  };
  const container = el("div");
  renderSearchResults(container, state);
  const texts = allTexts(container);
  assert.ok(texts.some((t) => t.includes("pump-001")));
  assert.ok(texts.some((t) => t.includes("WO-0001") && t.includes("Fix pump") && t.includes("open")));
});

test("renderSearchResults with all empty lists appends P No matches as second child", () => {
  const state = {
    dashboard: null,
    search: { query: "nothing", assets: [], work_orders: [], parts: [] },
    audit: [],
    viewerId: null,
    error: null,
  };
  const container = el("div");
  renderSearchResults(container, state);
  assert.ok(container.children.some((c) => c.tagName === "p" && c.textContent === "No matches."));
});

test("renderAuditEvents with audit data: LI contains entity type, operation, and timestamp", () => {
  const state = {
    audit: [{ id: "aud-1", actor_id: "user-111", entity_type: "site", entity_id: "site-1", operation: "site.created", details: { code: "site-1" }, created_at: "2026-11-13T12:00:01Z" }],
    viewerId: null,
    error: null,
  };
  const container = el("div");
  renderAuditEvents(container, state);
  assert.ok(allTexts(container).some((t) => t.includes("site") && t.includes("site.created") && t.includes("2026-11-13T12:00:01Z")));
});

test("renderDashboard with state.error appends P before data", () => {
  const state = setReportingError(createReportingState(), "something went wrong");
  const container = el("div");
  renderDashboard(container, state);
  assert.ok(allTexts(container).some((t) => t.includes("something went wrong")));
  assert.ok(!allTexts(container).some((t) => t.includes("Total work orders:")));
  const cleared = clearReportingError(state);
  assert.equal(cleared.error, null);
});
