import test from "node:test";
import assert from "node:assert/strict";

import {
  MOVEMENT_OPERATIONS,
  createInventoryState,
  selectBalance,
  setLowStockThreshold,
  setInventoryError,
  clearInventoryError,
  setInventoryConflict,
  clearInventoryConflict,
  balanceId,
  selectedBalance,
  availableQuantity,
  formatBalanceLine,
  formatSignedDelta,
  formatMovementLine,
  lowStockBalances,
  renderInventoryBalances,
  renderMovements,
  renderLowStock,
} from "../../web/js/inventory.mjs";

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

function makeBalance(overrides = {}) {
  return {
    part_id: "prt-1",
    part_sku: "bolt-m8",
    stock_location_id: "loc-1",
    location_code: "main",
    on_hand: 4,
    reserved: 1,
    version: 3,
    ...overrides,
  };
}

test("createInventoryState returns the empty shape with no storage field", () => {
  const state = createInventoryState();
  assert.deepEqual(state, {
    balances: [],
    movements: [],
    selectedBalanceId: null,
    lowStockThreshold: 0,
    error: null,
    conflict: null,
  });
  assert.equal("token" in state, false);
  assert.equal("storage" in state, false);
});

test("selectBalance selects by composite balance id", () => {
  const state = createInventoryState();
  const balance = makeBalance();
  const withBalance = { ...state, balances: [balance] };
  const next = selectBalance(withBalance, balanceId(balance));
  assert.equal(next.selectedBalanceId, "prt-1@loc-1");
  assert.equal(selectedBalance(next), balance);
  assert.equal(selectedBalance(state), null);
});

test("availableQuantity is derived as on_hand minus reserved", () => {
  assert.equal(availableQuantity(makeBalance({ on_hand: 4, reserved: 1 })), 3);
  assert.equal(availableQuantity(makeBalance({ on_hand: 2, reserved: 2 })), 0);
});

test("formatBalanceLine shows on_hand, reserved, and available consistently", () => {
  const line = formatBalanceLine(makeBalance({ on_hand: 4, reserved: 1 }));
  assert.equal(
    line,
    "bolt-m8 @ main: on_hand 4, reserved 1, available 3"
  );
});

test("formatSignedDelta prefixes non-negative deltas with plus", () => {
  assert.equal(formatSignedDelta(4), "+4");
  assert.equal(formatSignedDelta(0), "+0");
  assert.equal(formatSignedDelta(-4), "-4");
});

test("formatMovementLine shows both ledger deltas", () => {
  assert.equal(
    formatMovementLine({ operation: "reserve", on_hand_delta: 0, reserved_delta: 4 }),
    "reserve: on_hand +0, reserved +4"
  );
  assert.equal(
    formatMovementLine({ operation: "consume", on_hand_delta: -4, reserved_delta: -4 }),
    "consume: on_hand -4, reserved -4"
  );
});

test("setLowStockThreshold accepts non-negative integers and rejects the rest", () => {
  const state = createInventoryState();
  assert.equal(setLowStockThreshold(state, 2).lowStockThreshold, 2);
  assert.equal(setLowStockThreshold(state, 0).lowStockThreshold, 0);
  assert.equal(
    setLowStockThreshold(state, -1).error,
    "low-stock threshold must be a non-negative integer"
  );
  assert.equal(
    setLowStockThreshold(state, 1.5).error,
    "low-stock threshold must be a non-negative integer"
  );
});

test("lowStockBalances filters by available <= threshold", () => {
  const state = { ...createInventoryState(), lowStockThreshold: 1 };
  const balances = [
    makeBalance({ part_id: "prt-1", on_hand: 4, reserved: 1 }),
    makeBalance({ part_id: "prt-2", on_hand: 5, reserved: 1 }),
    makeBalance({ part_id: "prt-3", on_hand: 2, reserved: 2 }),
  ];
  const low = lowStockBalances({ ...state, balances });
  assert.deepEqual(
    low.map((balance) => balance.part_id),
    ["prt-3"]
  );
});

test("error and conflict setters set and clear their region", () => {
  let state = createInventoryState();
  state = setInventoryError(state, "boom");
  assert.equal(state.error, "boom");
  state = clearInventoryError(state);
  assert.equal(state.error, null);
  state = setInventoryConflict(state, "stale");
  assert.equal(state.conflict, "stale");
  state = clearInventoryConflict(state);
  assert.equal(state.conflict, null);
});

test("renderInventoryBalances builds one button per balance with consistent numbers", () => {
  const document = makeStubDocument();
  globalThis.document = document;
  const container = makeStubElement("DIV");
  const state = { ...createInventoryState(), balances: [makeBalance()] };
  let selected = null;
  renderInventoryBalances(container, state, {
    onSelect: (id) => {
      selected = id;
    },
  });
  const list = container.children[0];
  const item = list.children[0];
  const button = item.children[0];
  assert.equal(button.textContent, "bolt-m8 @ main: on_hand 4, reserved 1, available 3");
  button.listeners["click"]();
  assert.equal(selected, "prt-1@loc-1");
  delete globalThis.document;
});

test("renderInventoryBalances shows an empty message without balances", () => {
  const document = makeStubDocument();
  globalThis.document = document;
  const container = makeStubElement("DIV");
  renderInventoryBalances(container, createInventoryState(), { onSelect: () => {} });
  assert.equal(container.children.length, 2);
  assert.equal(container.children[1].textContent, "No stock balances yet.");
  delete globalThis.document;
});

test("renderMovements lists movements through the shared formatter", () => {
  const document = makeStubDocument();
  globalThis.document = document;
  const container = makeStubElement("DIV");
  const state = {
    ...createInventoryState(),
    movements: [
      { operation: "receive", on_hand_delta: 4, reserved_delta: 0 },
      { operation: "consume", on_hand_delta: -1, reserved_delta: -1 },
    ],
  };
  renderMovements(container, state, {});
  const list = container.children[0];
  assert.equal(list.children[0].textContent, "receive: on_hand +4, reserved +0");
  assert.equal(list.children[1].textContent, "consume: on_hand -1, reserved -1");
  delete globalThis.document;
});

test("renderMovements shows an empty message without movements", () => {
  const document = makeStubDocument();
  globalThis.document = document;
  const container = makeStubElement("DIV");
  renderMovements(container, createInventoryState(), {});
  assert.equal(container.children[1].textContent, "No stock movements yet.");
  delete globalThis.document;
});

test("renderLowStock lists only balances at or below the threshold", () => {
  const document = makeStubDocument();
  globalThis.document = document;
  const container = makeStubElement("DIV");
  const state = {
    ...createInventoryState(),
    lowStockThreshold: 1,
    balances: [
      makeBalance({ part_id: "prt-1", on_hand: 2, reserved: 2 }),
      makeBalance({ part_id: "prt-2", on_hand: 5, reserved: 1 }),
    ],
  };
  renderLowStock(container, state, {});
  assert.equal(container.children[0].textContent, "Low stock (available <= 1)");
  const list = container.children[1];
  assert.equal(list.children.length, 1);
  assert.equal(
    list.children[0].textContent,
    "bolt-m8 @ main: on_hand 2, reserved 2, available 0"
  );
  delete globalThis.document;
});

test("renderLowStock shows an empty message when nothing is low", () => {
  const document = makeStubDocument();
  globalThis.document = document;
  const container = makeStubElement("DIV");
  const state = {
    ...createInventoryState(),
    lowStockThreshold: 0,
    balances: [makeBalance({ on_hand: 4, reserved: 1 })],
  };
  renderLowStock(container, state, {});
  assert.equal(container.children[0].textContent, "Low stock (available <= 0)");
  assert.equal(container.children[1].children.length, 0);
  assert.equal(container.children[2].textContent, "No low-stock balances.");
  delete globalThis.document;
});

test("render functions never write innerHTML", () => {
  const document = makeStubDocument();
  globalThis.document = document;
  const containers = [makeStubElement("DIV"), makeStubElement("DIV"), makeStubElement("DIV")];
  const state = {
    ...createInventoryState(),
    balances: [makeBalance()],
    movements: [{ operation: "receive", on_hand_delta: 4, reserved_delta: 0 }],
  };
  renderInventoryBalances(containers[0], state, { onSelect: () => {} });
  renderMovements(containers[1], state, {});
  renderLowStock(containers[2], state, {});
  for (const container of containers) {
    for (const child of container.children) {
      assert.equal(child.innerHTML_written ?? "", "");
    }
  }
  delete globalThis.document;
});
