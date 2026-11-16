import test from "node:test";
import assert from "node:assert/strict";

import {
  REQUEST_STATUSES,
  createPurchasingState,
  setViewer,
  setPurchasingError,
  clearPurchasingError,
  setPurchasingConflict,
  clearPurchasingConflict,
  canApprove,
  formatRequestLine,
  formatOrderLine,
  formatReceiptLine,
  renderRequests,
  renderOrders,
  renderReceipts,
} from "../../web/js/purchasing.mjs";

function makeStubElement(tagName) {
  return {
    tagName,
    children: [],
    attributes: {},
    textContent: "",
    listeners: {},
    appendChild(child) {
      this.children.push(child);
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    addEventListener(type, handler) {
      this.listeners[type] = handler;
    },
  };
}

function makeStubDocument() {
  return {
    createElement(tagName) {
      const element = makeStubElement(tagName);
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

function withDocument(run) {
  const document = makeStubDocument();
  globalThis.document = document;
  try {
    return run();
  } finally {
    delete globalThis.document;
  }
}

function makeRequest(overrides = {}) {
  return {
    id: "prq-1",
    requested_by: "user-111",
    status: "submitted",
    total_cents: 25000,
    ...overrides,
  };
}

function makeOrder(overrides = {}) {
  return {
    id: "por-1",
    status: "open",
    total_cents: 25000,
    ...overrides,
  };
}

function makeReceipt(overrides = {}) {
  return {
    id: "rcp-1",
    purchase_order_id: "por-1",
    lines: [
      { quantity: 4, unit_cost_cents: 2500 },
      { quantity: 6, unit_cost_cents: 1000 },
    ],
    ...overrides,
  };
}

test("createPurchasingState returns the empty shape with no storage field", () => {
  const state = createPurchasingState();
  assert.deepEqual(state, {
    requests: [],
    orders: [],
    receipts: [],
    viewerId: null,
    error: null,
    conflict: null,
  });
  assert.equal(Object.hasOwn(state, "localStorage"), false);
  assert.equal(Object.hasOwn(state, "sessionStorage"), false);
});

test("REQUEST_STATUSES lists the six lifecycle states", () => {
  assert.deepEqual(
    [...REQUEST_STATUSES],
    ["draft", "submitted", "approved", "rejected", "cancelled", "ordered"]
  );
  assert.equal(REQUEST_STATUSES.length, 6);
});

test("setViewer updates the viewer without mutating the input", () => {
  const state = createPurchasingState();
  const next = setViewer(state, "user-222");
  assert.equal(next.viewerId, "user-222");
  assert.equal(state.viewerId, null);
  assert.deepEqual(state, createPurchasingState());
});

test("canApprove disables self-approval and non-submitted statuses", () => {
  const request = makeRequest();

  const selfState = setViewer(createPurchasingState(), "user-111");
  assert.equal(canApprove(selfState, request), false);

  for (const status of ["approved", "draft", "ordered"]) {
    const other = makeRequest({ status });
    const state = setViewer(createPurchasingState(), "user-222");
    assert.equal(canApprove(state, other), false, `status ${status}`);
  }

  const otherViewerState = setViewer(createPurchasingState(), "user-222");
  assert.equal(canApprove(otherViewerState, request), true);

  const noViewerState = createPurchasingState();
  assert.equal(canApprove(noViewerState, request), false);
});

test("canApprove requires the exactly submitted status, not a prefix", () => {
  const state = setViewer(createPurchasingState(), "user-222");
  assert.equal(canApprove(state, makeRequest({ status: "submitted " })), false);
  assert.equal(canApprove(state, makeRequest({ status: "Submitted" })), false);
  assert.equal(canApprove(state, makeRequest({ status: "submitted" })), true);
});

test("formatters show ids, statuses, and integer-cent totals", () => {
  const requestLine = formatRequestLine(makeRequest());
  assert.match(requestLine, /prq-1/);
  assert.match(requestLine, /submitted/);
  assert.match(requestLine, /25000 cents/);

  const orderLine = formatOrderLine(makeOrder());
  assert.match(orderLine, /por-1/);
  assert.match(orderLine, /open/);
  assert.match(orderLine, /25000 cents/);

  const receiptLine = formatReceiptLine(makeReceipt());
  assert.match(receiptLine, /rcp-1/);
  assert.match(receiptLine, /por-1/);
  assert.match(receiptLine, /2 line\(s\)/);
  assert.match(receiptLine, /16000 cents/);
});

test("renderRequests lists rows as UL of LI and never writes innerHTML", () => {
  const container = makeStubElement("DIV");
  const state = { ...createPurchasingState(), requests: [makeRequest()] };
  withDocument(() => renderRequests(container, state, { onApprove: () => {} }));
  const list = container.children[0];
  assert.equal(list.tagName, "ul");
  assert.equal(list.children.length, 1);
  assert.equal(list.children[0].tagName, "li");
  assert.match(list.children[0].textContent, /prq-1/);
  for (const node of [container, list]) {
    assert.equal(node.innerHTML_written ?? "", "");
  }
});

test("renderRequests hides the approve button for the requester", () => {
  const container = makeStubElement("DIV");
  const state = {
    ...createPurchasingState(),
    viewerId: "user-111",
    requests: [makeRequest()],
  };
  withDocument(() => renderRequests(container, state, { onApprove: () => {} }));
  const item = container.children[0].children[0];
  assert.deepEqual(item.children, []);
});

test("renderRequests shows one approve button for another viewer", () => {
  const container = makeStubElement("DIV");
  const state = {
    ...createPurchasingState(),
    viewerId: "user-222",
    requests: [makeRequest()],
  };
  let approved = null;
  withDocument(() =>
    renderRequests(container, state, {
      onApprove: (id) => {
        approved = id;
      },
    })
  );
  const button = container.children[0].children[0].children[0];
  assert.match(button.textContent, /^Approve prq-1$/);
  assert.equal(button.attributes.type, undefined);
  button.listeners["click"]();
  assert.equal(approved, "prq-1");
});

test("renderRequests builds the empty message as the second child", () => {
  const container = makeStubElement("DIV");
  withDocument(() => renderRequests(container, createPurchasingState(), { onApprove: () => {} }));
  assert.equal(container.children.length, 2);
  const empty = container.children[1];
  assert.equal(empty.tagName, "p");
  assert.equal(empty.textContent, "No purchase requests yet.");
});

test("renderOrders and renderReceipts append lists and empty messages", () => {
  const container = makeStubElement("DIV");
  withDocument(() => renderOrders(container, createPurchasingState(), {}));
  withDocument(() => renderReceipts(container, createPurchasingState(), {}));
  assert.equal(container.children.length, 4);
  assert.equal(container.children[0].children.length, 0);
  assert.equal(container.children[1].tagName, "p");
  assert.equal(container.children[1].textContent, "No purchase orders yet.");
  assert.equal(container.children[2].children.length, 0);
  assert.equal(container.children[3].tagName, "p");
  assert.equal(container.children[3].textContent, "No receipts yet.");
});

test("renderOrders and renderReceipts ignore the third argument", () => {
  const container = makeStubElement("DIV");
  withDocument(() => renderOrders(container, createPurchasingState(), undefined));
  withDocument(() => renderReceipts(container, createPurchasingState(), null));
  assert.equal(container.children.length, 4);
  assert.equal(container.children[1].textContent, "No purchase orders yet.");
  assert.equal(container.children[3].textContent, "No receipts yet.");
});

test("error and conflict setters are separate and clearable", () => {
  let state = setPurchasingConflict(createPurchasingState(), "stale");
  assert.equal(state.conflict, "stale");
  assert.equal(state.error, null);

  state = setPurchasingError(state, "boom");
  assert.equal(state.error, "boom");
  assert.equal(state.conflict, "stale");

  state = clearPurchasingConflict(state);
  assert.equal(state.conflict, null);
  assert.equal(state.error, "boom");

  state = clearPurchasingError(state);
  assert.equal(state.error, null);
});
