import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  WORK_ORDER_STATUSES,
  WORK_ORDER_TRANSITIONS,
  TECHNICIAN_TRANSITIONS,
  createWorkOrdersState,
  selectWorkOrder,
  setWorkOrderError,
  clearWorkOrderError,
  setWorkOrderConflict,
  clearWorkOrderConflict,
  selectedOrder,
  availableActions,
  actionButtonLabel,
  formatWorkOrderLine,
  renderWorkOrderBoard,
  renderWorkOrderDetail,
} from "../../web/js/workorders.mjs";

function makeStubElement(tagName) {
  return {
    tagName,
    children: [],
    attributes: {},
    textContent: "",
    appended: [],
    appendChild(child) {
      this.children.push(child);
      this.appended.push(child);
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    addEventListener(type, handler) {
      this.listeners = this.listeners || {};
      this.listeners[type] = handler;
    },
  };
}

function makeStubDocument() {
  return {
    createElement(tagName) {
      const element = makeStubElement(String(tagName).toUpperCase());
      element.innerHTML_written = "";
      Object.defineProperty(element, "innerHTML", {
        set(value) {
          this.innerHTML_written = value;
        },
        get() {
          return this.innerHTML_written;
        },
      });
      return element;
    },
  };
}

const ORDER = {
  id: "wo-1",
  number: "wo-100",
  title: "Rebuild pump",
  status: "assigned",
  version: 2,
};

test("createWorkOrdersState returns the empty shape with no storage field", () => {
  const state = createWorkOrdersState();
  assert.deepEqual(state, {
    orders: [],
    selectedOrderId: null,
    error: null,
    conflict: null,
  });
  assert.equal("token" in state, false);
  assert.equal("storage" in state, false);
});

test("selectWorkOrder sets the id without mutating the input state", () => {
  const state = createWorkOrdersState();
  const next = selectWorkOrder(state, "wo-1");
  assert.equal(next.selectedOrderId, "wo-1");
  assert.equal(state.selectedOrderId, null);
});

test("error and conflict setters/clearers keep error and conflict separate", () => {
  let state = createWorkOrdersState();
  state = setWorkOrderError(state, "Name is required.");
  assert.equal(state.error, "Name is required.");
  assert.equal(state.conflict, null);
  state = setWorkOrderConflict(state, "work order version conflict; refresh and retry");
  assert.equal(state.conflict, "work order version conflict; refresh and retry");
  assert.equal(state.error, "Name is required.");
  state = clearWorkOrderError(state);
  assert.equal(state.error, null);
  assert.equal(state.conflict, "work order version conflict; refresh and retry");
  state = clearWorkOrderConflict(state);
  assert.equal(state.conflict, null);
});

test("selectedOrder returns the matching order or null", () => {
  const state = createWorkOrdersState();
  state.orders.push(ORDER);
  const withSelection = selectWorkOrder(state, "wo-1");
  assert.deepEqual(selectedOrder(withSelection), ORDER);
  assert.equal(selectedOrder(state), null);
});

test("availableActions: supervisor sees the full transition map per state", () => {
  assert.deepEqual(
    availableActions({ ...ORDER, status: "open" }, "supervisor").map((a) => a.toStatus),
    ["assigned", "cancelled"],
  );
  assert.deepEqual(
    availableActions({ ...ORDER, status: "assigned" }, "supervisor").map((a) => a.toStatus),
    ["in_progress", "open", "cancelled"],
  );
  assert.deepEqual(
    availableActions({ ...ORDER, status: "in_progress" }, "supervisor").map((a) => a.toStatus),
    ["blocked", "completed", "cancelled"],
  );
  assert.deepEqual(
    availableActions({ ...ORDER, status: "blocked" }, "supervisor").map((a) => a.toStatus),
    ["in_progress", "cancelled"],
  );
  assert.deepEqual(
    availableActions({ ...ORDER, status: "completed" }, "supervisor").map((a) => a.toStatus),
    ["closed", "in_progress"],
  );
  assert.deepEqual(
    availableActions({ ...ORDER, status: "closed" }, "supervisor").map((a) => a.toStatus),
    ["open"],
  );
  assert.deepEqual(availableActions({ ...ORDER, status: "cancelled" }, "supervisor"), []);
  assert.equal(availableActions(null, "supervisor").length, 0);
});

test("availableActions: technician sees only start/block/unblock, never close or cancel", () => {
  assert.deepEqual(
    availableActions({ ...ORDER, status: "assigned" }, "technician").map((a) => a.toStatus),
    ["in_progress"],
  );
  assert.deepEqual(
    availableActions({ ...ORDER, status: "in_progress" }, "technician").map((a) => a.toStatus),
    ["blocked"],
  );
  assert.deepEqual(
    availableActions({ ...ORDER, status: "blocked" }, "technician").map((a) => a.toStatus),
    ["in_progress"],
  );
  assert.deepEqual(availableActions({ ...ORDER, status: "open" }, "technician"), []);
  assert.deepEqual(availableActions({ ...ORDER, status: "completed" }, "technician"), []);
  assert.deepEqual(availableActions({ ...ORDER, status: "closed" }, "technician"), []);
  assert.deepEqual(availableActions({ ...ORDER, status: "cancelled" }, "technician"), []);
});

test("availableActions carries the current status and version as the expected version", () => {
  const actions = availableActions(ORDER, "supervisor");
  for (const action of actions) {
    assert.equal(action.fromStatus, "assigned");
    assert.equal(action.expectedVersion, 2);
  }
  assert.equal(actions[0].label, "Start work");
});

test("actionButtonLabel maps every transition pair and falls back to the status", () => {
  assert.equal(actionButtonLabel("assigned", "in_progress"), "Start work");
  assert.equal(actionButtonLabel("in_progress", "blocked"), "Block");
  assert.equal(actionButtonLabel("blocked", "in_progress"), "Unblock");
  assert.equal(actionButtonLabel("in_progress", "completed"), "Mark completed");
  assert.equal(actionButtonLabel("completed", "closed"), "Close");
  assert.equal(actionButtonLabel("closed", "open"), "Reopen");
  assert.equal(actionButtonLabel("open", "cancelled"), "Cancel");
  assert.equal(actionButtonLabel("mystery", "dest"), "dest");
});

test("formatWorkOrderLine renders number, title, and visible status text", () => {
  assert.equal(formatWorkOrderLine(ORDER), "wo-100 — Rebuild pump [assigned]");
});

test("TECHNICIAN_TRANSITIONS never reach terminal or supervisor-only states", () => {
  for (const targets of Object.values(TECHNICIAN_TRANSITIONS)) {
    for (const target of targets) {
      assert.ok(["in_progress", "blocked"].includes(target));
    }
  }
  assert.equal("cancelled" in TECHNICIAN_TRANSITIONS, false);
  assert.equal("completed" in TECHNICIAN_TRANSITIONS, false);
});

test("WORK_ORDER_TRANSITIONS covers exactly the seven statuses", () => {
  assert.deepEqual(Object.keys(WORK_ORDER_TRANSITIONS).sort(), [...WORK_ORDER_STATUSES].sort());
  assert.equal(WORK_ORDER_STATUSES.length, 7);
});

test("renderWorkOrderBoard builds one keyboard-reachable button per order and an empty state", () => {
  const document = makeStubDocument();
  const savedDocument = globalThis.document;
  globalThis.document = document;
  try {
    const state = createWorkOrdersState();
    state.orders.push(ORDER);
    const container = makeStubElement("div");
    renderWorkOrderBoard(container, state, { onSelect: () => {} });
    const list = container.appended[0];
    assert.equal(list.tagName, "UL");
    const button = list.children[0].children[0];
    assert.equal(button.tagName, "BUTTON");
    assert.equal(button.type, "button");
    assert.equal(button.textContent, "wo-100 — Rebuild pump [assigned]");

    const emptyContainer = makeStubElement("div");
    renderWorkOrderBoard(emptyContainer, createWorkOrdersState(), { onSelect: () => {} });
    const emptyParagraph = emptyContainer.appended.find((element) => element.tagName === "P");
    assert.equal(emptyParagraph.textContent, "No work orders yet.");
  } finally {
    globalThis.document = savedDocument;
  }
});

test("renderWorkOrderDetail: action buttons match state and role, wired with version", () => {
  const document = makeStubDocument();
  const savedDocument = globalThis.document;
  globalThis.document = document;
  try {
    let state = createWorkOrdersState();
    state.orders.push(ORDER);
    state = selectWorkOrder(state, "wo-1");
    const received = [];
    const container = makeStubElement("div");
    const section = renderWorkOrderDetail(container, state, {
      role: "supervisor",
      onAction: (payload) => received.push(payload),
      onRefresh: () => {},
    });
    assert.equal(section.tagName, "SECTION");
    const buttons = section.children.filter((child) => child.tagName === "BUTTON");
    assert.deepEqual(buttons.map((button) => button.textContent), ["Start work", "Unassign", "Cancel"]);
    buttons[0].listeners.click();
    assert.deepEqual(received, [{ toStatus: "in_progress", expectedVersion: 2 }]);
  } finally {
    globalThis.document = savedDocument;
  }
});

test("renderWorkOrderDetail: technician actions differ from supervisor actions for the same order", () => {
  const document = makeStubDocument();
  const savedDocument = globalThis.document;
  globalThis.document = document;
  try {
    let state = createWorkOrdersState();
    state.orders.push(ORDER);
    state = selectWorkOrder(state, "wo-1");
    const container = makeStubElement("div");
    const section = renderWorkOrderDetail(container, state, {
      role: "technician",
      onAction: () => {},
      onRefresh: () => {},
    });
    const buttons = section.children.filter((child) => child.tagName === "BUTTON");
    assert.deepEqual(buttons.map((button) => button.textContent), ["Start work"]);
  } finally {
    globalThis.document = savedDocument;
  }
});

test("renderWorkOrderDetail: conflict shows an actionable alert with a Refresh button wired to onRefresh", () => {
  const document = makeStubDocument();
  const savedDocument = globalThis.document;
  globalThis.document = document;
  try {
    let state = createWorkOrdersState();
    state.orders.push(ORDER);
    state = selectWorkOrder(state, "wo-1");
    state = setWorkOrderConflict(state, "work order version conflict; refresh and retry");
    let refreshed = 0;
    const container = makeStubElement("div");
    const section = renderWorkOrderDetail(container, state, {
      role: "supervisor",
      onAction: () => {},
      onRefresh: () => {
        refreshed += 1;
      },
    });
    const conflictRegion = section.children.find(
      (child) => child.tagName === "P" && child.textContent.includes("refresh and retry"),
    );
    assert.notEqual(conflictRegion, undefined);
    assert.equal(conflictRegion.attributes.role, "alert");
    const refresh = conflictRegion.children.find((child) => child.tagName === "BUTTON");
    assert.equal(refresh.textContent, "Refresh");
    refresh.listeners.click();
    assert.equal(refreshed, 1);
    const errorRegion = section.children.filter((child) => child.tagName === "P").pop();
    assert.notEqual(errorRegion, conflictRegion);
  } finally {
    globalThis.document = savedDocument;
  }
});

test("renderWorkOrderDetail: no selection renders the empty prompt and no buttons", () => {
  const document = makeStubDocument();
  const savedDocument = globalThis.document;
  globalThis.document = document;
  try {
    const container = makeStubElement("div");
    const result = renderWorkOrderDetail(container, createWorkOrdersState(), {
      role: "supervisor",
      onAction: () => {},
      onRefresh: () => {},
    });
    assert.equal(result, null);
    const paragraph = container.appended.find((element) => element.tagName === "P");
    assert.equal(paragraph.textContent, "Select a work order to see its detail.");
  } finally {
    globalThis.document = savedDocument;
  }
});

test("no storage access: module source contains neither localStorage nor sessionStorage and no innerHTML", () => {
  const source = readFileSync(new URL("../../web/js/workorders.mjs", import.meta.url), "utf8");
  assert.equal(source.includes("localStorage"), false);
  assert.equal(source.includes("sessionStorage"), false);
  assert.equal(source.includes("innerHTML"), false);
});
