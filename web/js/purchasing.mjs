// Pure ES module for the purchasing screen: purchase requests, purchase
// orders, and receipts. No DOM work happens at import time; all DOM work
// happens in the functions the caller invokes (the render* functions
// below). Render functions build controls with createElement/textContent
// ONLY (never raw inner HTML markup with dynamic user text). State is
// in-memory only; the UI consumes domain rows snake_case exactly as the
// server serializes them. The self-approval rule lives here in ONE place
// (canApprove) and every render path derives approval through it, so the
// rule is applied consistently everywhere. Server denial is tested
// separately; here the UI rule is the accept core. No fetch/API calls;
// no browser web storage APIs anywhere.

export const REQUEST_STATUSES = [
  "draft",
  "submitted",
  "approved",
  "rejected",
  "cancelled",
  "ordered",
];

export function createPurchasingState() {
  return {
    requests: [],
    orders: [],
    receipts: [],
    viewerId: null,
    error: null,
    conflict: null,
  };
}

export function setViewer(state, viewerId) {
  return { ...state, viewerId };
}

export function setPurchasingError(state, message) {
  return { ...state, error: message };
}

export function clearPurchasingError(state) {
  return { ...state, error: null };
}

export function setPurchasingConflict(state, message) {
  return { ...state, conflict: message };
}

export function clearPurchasingConflict(state) {
  return { ...state, conflict: null };
}

// The single source of truth for the UI approval rule: only a viewer who
// is set, is NOT the requester, and sees a request in exactly the
// "submitted" status may approve. Every render path derives through this
// helper, so hiding an approve button can never bypass it here.
export function canApprove(state, request) {
  return (
    state.viewerId !== null &&
    request.requested_by !== state.viewerId &&
    request.status === "submitted"
  );
}

export function formatRequestLine(request) {
  return `Purchase request ${request.id}: status ${request.status}, total ${request.total_cents} cents`;
}

export function formatOrderLine(order) {
  return `Purchase order ${order.id}: status ${order.status}, total ${order.total_cents} cents`;
}

export function formatReceiptLine(receipt) {
  const total = receipt.lines.reduce(
    (sum, line) => sum + line.quantity * line.unit_cost_cents,
    0
  );
  const count = receipt.lines.length;
  return `Receipt ${receipt.id} for ${receipt.purchase_order_id}: ${count} line(s), total ${total} cents`;
}

export function renderRequests(container, state, handlers) {
  const list = document.createElement("ul");
  for (const request of state.requests) {
    const item = document.createElement("li");
    item.textContent = formatRequestLine(request);
    if (canApprove(state, request)) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `Approve ${request.id}`;
      button.addEventListener("click", () => {
        handlers.onApprove(request.id);
      });
      item.appendChild(button);
    }
    list.appendChild(item);
  }
  container.appendChild(list);
  if (state.requests.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No purchase requests yet.";
    container.appendChild(empty);
  }
}

export function renderOrders(container, state, handlers = {}) {
  const list = document.createElement("ul");
  for (const order of state.orders) {
    const item = document.createElement("li");
    item.textContent = formatOrderLine(order);
    list.appendChild(item);
  }
  container.appendChild(list);
  if (state.orders.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No purchase orders yet.";
    container.appendChild(empty);
  }
}

export function renderReceipts(container, state, handlers = {}) {
  const list = document.createElement("ul");
  for (const receipt of state.receipts) {
    const item = document.createElement("li");
    item.textContent = formatReceiptLine(receipt);
    list.appendChild(item);
  }
  container.appendChild(list);
  if (state.receipts.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No receipts yet.";
    container.appendChild(empty);
  }
}
