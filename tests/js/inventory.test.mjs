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
