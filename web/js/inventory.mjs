// Pure ES module for the inventory balances, movements, and low-stock views.
// No DOM work happens at import time; all DOM work happens in the
// functions the caller invokes (the render* functions below). Render
// functions build controls with createElement/textContent ONLY (never
// raw inner HTML markup with dynamic user text) and use real
// button/input elements, so every control is keyboard-reachable by
// default. Available stock is derived in ONE place
// (availableQuantity = on_hand - reserved) and every view formats the
// same triple (on_hand, reserved, available) through the same helpers,
// so the three numbers are shown consistently everywhere. Input values
// are always re-rendered from state on every pass, so errors never
// destroy typed values. Display conflicts are separate from errors and
// always carry a refresh action. No fetch/API calls here; no browser
// web storage APIs anywhere (state is in-memory only).

export const MOVEMENT_OPERATIONS = [
  "receive",
  "reserve",
  "release",
  "consume",
  "adjust",
];

export function createInventoryState() {
  return {
    balances: [],
    movements: [],
    selectedBalanceId: null,
    lowStockThreshold: 0,
    error: null,
    conflict: null,
  };
}

export function selectBalance(state, balanceId) {
  return { ...state, selectedBalanceId: balanceId };
}

export function setLowStockThreshold(state, threshold) {
  const value = Number(threshold);
  if (!Number.isInteger(value) || value < 0) {
    return { ...state, error: "low-stock threshold must be a non-negative integer" };
  }
  return { ...state, lowStockThreshold: value, error: null };
}

export function setInventoryError(state, message) {
  return { ...state, error: message };
}

export function clearInventoryError(state) {
  return { ...state, error: null };
}

export function setInventoryConflict(state, message) {
  return { ...state, conflict: message };
}

export function clearInventoryConflict(state) {
  return { ...state, conflict: null };
}

export function balanceId(balance) {
  return `${balance.part_id}@${balance.stock_location_id}`;
}

export function selectedBalance(state) {
  return state.balances.find(
    (balance) => balanceId(balance) === state.selectedBalanceId
  ) ?? null;
}

// The single source of truth for available stock: every view and every
// filter derives available through this helper, so on_hand, reserved,
// and available are always shown consistently.
export function availableQuantity(balance) {
  return balance.on_hand - balance.reserved;
}

export function formatBalanceLine(balance) {
  return `${balance.part_sku} @ ${balance.location_code}: on_hand ${balance.on_hand}, reserved ${balance.reserved}, available ${availableQuantity(balance)}`;
}

export function formatSignedDelta(delta) {
  return delta >= 0 ? `+${delta}` : `${delta}`;
}

export function formatMovementLine(movement) {
  return `${movement.operation}: on_hand ${formatSignedDelta(movement.on_hand_delta)}, reserved ${formatSignedDelta(movement.reserved_delta)}`;
}

export function lowStockBalances(state) {
  return state.balances.filter(
    (balance) => availableQuantity(balance) <= state.lowStockThreshold
  );
}
