// Pure ES module for the work-order board, detail, and action UI logic.
// No DOM work happens at import time; all DOM work happens in the
// functions the caller invokes (the render* functions below). Render
// functions build controls with createElement/textContent ONLY (never
// raw inner HTML markup with dynamic user text) and use real
// button/input/select elements, so every control is keyboard-reachable
// by default. Input values are always re-rendered from state on every
// pass, so errors never destroy typed values. Display conflicts are
// separate from errors and always carry a refresh action. No fetch/API
// calls here; no browser web storage APIs anywhere (state is in-memory
// only).

export const WORK_ORDER_STATUSES = [
  "open",
  "assigned",
  "in_progress",
  "blocked",
  "completed",
  "closed",
  "cancelled",
];

export const WORK_ORDER_TRANSITIONS = {
  open: ["assigned", "cancelled"],
  assigned: ["in_progress", "open", "cancelled"],
  in_progress: ["blocked", "completed", "cancelled"],
  blocked: ["in_progress", "cancelled"],
  completed: ["closed", "in_progress"],
  closed: ["open"],
  cancelled: [],
};

// Technicians work on orders (start, block, unblock); closure, reopening
// and cancellation stay with supervisors and admins (spec role model).
export const TECHNICIAN_TRANSITIONS = {
  assigned: ["in_progress"],
  in_progress: ["blocked"],
  blocked: ["in_progress"],
};

const ACTION_LABELS = {
  "assigned>in_progress": "Start work",
  "in_progress>blocked": "Block",
  "blocked>in_progress": "Unblock",
  "in_progress>completed": "Mark completed",
  "completed>closed": "Close",
  "completed>in_progress": "Send back to work",
  "open>assigned": "Assign",
  "assigned>open": "Unassign",
  "open>cancelled": "Cancel",
  "assigned>cancelled": "Cancel",
  "in_progress>cancelled": "Cancel",
  "blocked>cancelled": "Cancel",
  "closed>open": "Reopen",
};

export function createWorkOrdersState() {
  return {
    orders: [],
    selectedOrderId: null,
    error: null,
    conflict: null,
  };
}

export function selectWorkOrder(state, orderId) {
  return { ...state, selectedOrderId: orderId };
}

export function setWorkOrderError(state, message) {
  return { ...state, error: message };
}

export function clearWorkOrderError(state) {
  return { ...state, error: null };
}

export function setWorkOrderConflict(state, message) {
  return { ...state, conflict: message };
}

export function clearWorkOrderConflict(state) {
  return { ...state, conflict: null };
}

export function selectedOrder(state) {
  return state.orders.find((order) => order.id === state.selectedOrderId) ?? null;
}

export function availableActions(order, role) {
  if (!order) {
    return [];
  }
  const allowed = role === "technician"
    ? TECHNICIAN_TRANSITIONS[order.status] ?? []
    : WORK_ORDER_TRANSITIONS[order.status] ?? [];
  return allowed.map((toStatus) => ({
    fromStatus: order.status,
    toStatus,
    label: ACTION_LABELS[`${order.status}>${toStatus}`] ?? toStatus,
    expectedVersion: order.version,
  }));
}

export function actionButtonLabel(fromStatus, toStatus) {
  return ACTION_LABELS[`${fromStatus}>${toStatus}`] ?? toStatus;
}

export function formatWorkOrderLine(order) {
  return `${order.number} — ${order.title} [${order.status}]`;
}

export function renderWorkOrderBoard(container, state, handlers) {
  const list = document.createElement("ul");
  for (const order of state.orders) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = formatWorkOrderLine(order);
    button.addEventListener("click", () => {
      handlers.onSelect(order.id);
    });
    item.appendChild(button);
    list.appendChild(item);
  }
  container.appendChild(list);
  if (state.orders.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No work orders yet.";
    container.appendChild(empty);
  }
}

export function renderWorkOrderDetail(container, state, handlers) {
  const order = selectedOrder(state);
  if (!order) {
    const empty = document.createElement("p");
    empty.textContent = "Select a work order to see its detail.";
    container.appendChild(empty);
    return null;
  }
  const section = document.createElement("section");
  const heading = document.createElement("h2");
  heading.textContent = formatWorkOrderLine(order);
  section.appendChild(heading);

  const versionText = document.createElement("p");
  versionText.textContent = `Version ${order.version}`;
  section.appendChild(versionText);

  for (const action of availableActions(order, handlers.role)) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    button.addEventListener("click", () => {
      handlers.onAction({
        toStatus: action.toStatus,
        expectedVersion: action.expectedVersion,
      });
    });
    section.appendChild(button);
  }

  if (state.conflict) {
    const conflictRegion = document.createElement("p");
    conflictRegion.setAttribute("role", "alert");
    conflictRegion.setAttribute("aria-live", "assertive");
    conflictRegion.textContent = state.conflict;
    const refresh = document.createElement("button");
    refresh.type = "button";
    refresh.textContent = "Refresh";
    refresh.addEventListener("click", () => {
      handlers.onRefresh();
    });
    section.appendChild(conflictRegion);
    section.appendChild(refresh);
  }

  const errorRegion = document.createElement("p");
  errorRegion.setAttribute("role", "alert");
  errorRegion.setAttribute("aria-live", "assertive");
  errorRegion.textContent = state.error ?? "";
  section.appendChild(errorRegion);

  container.appendChild(section);
  return section;
}
