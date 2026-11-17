// Layer conventions (do not edit check.sh):
// SQLite with foreign keys, parameterized SQL. Audit is append-only.
// Immutable-style data: services return new objects, never mutate inputs.

export const WORK_ORDER_STATUSES = [
  "open",
  "assigned",
  "in_progress",
  "blocked",
  "completed",
  "closed",
  "cancelled",
];

export function createReportingState() {
  return {
    dashboard: null,
    search: null,
    audit: [],
    viewerId: null,
    error: null,
  };
}

export function setDashboard(state, dashboard) {
  return { ...state, dashboard };
}

export function setSearchResults(state, results) {
  return { ...state, search: results };
}

export function setAuditEvents(state, events) {
  return { ...state, audit: [...events] };
}

export function setReportingError(state, message) {
  return { ...state, error: message };
}

export function clearReportingError(state) {
  return { ...state, error: null };
}

export function formatWorkOrderLine(wo) {
  return `Work order ${wo.number}: ${wo.title} [${wo.status}]`;
}

export function renderDashboard(container, state, handlers = {}) {
  const list = document.createElement("ul");
  const d = state.dashboard;
  if (d) {
    for (const status of Object.keys(d.work_orders.by_status)) {
      const count = d.work_orders.by_status[status];
      if (count > 0) {
        const item = document.createElement("li");
        item.textContent = `${status}: ${count}`;
        list.appendChild(item);
      }
    }
    const total = document.createElement("li");
    total.textContent = `Total work orders: ${d.work_orders.total}`;
    list.appendChild(total);
    const assets = document.createElement("li");
    assets.textContent = `Assets: ${d.assets.total}`;
    list.appendChild(assets);
    const onHand = document.createElement("li");
    onHand.textContent = `Stock on hand: ${d.stock.on_hand}`;
    list.appendChild(onHand);
    const reserved = document.createElement("li");
    reserved.textContent = `Stock reserved: ${d.stock.reserved}`;
    list.appendChild(reserved);
    const labor = document.createElement("li");
    labor.textContent = `Labor cost: ${d.labor_cost_cents} cents`;
    list.appendChild(labor);
  }
  container.appendChild(list);
  if (!d) {
    const empty = document.createElement("p");
    empty.textContent = "No dashboard loaded yet.";
    container.appendChild(empty);
  }
}

export function renderSearchResults(container, state, handlers = {}) {
  const list = document.createElement("ul");
  const s = state.search;
  if (s) {
    for (const a of s.assets) {
      const item = document.createElement("li");
      item.textContent = `${a.tag} - ${a.name}`;
      list.appendChild(item);
    }
    for (const w of s.work_orders) {
      const item = document.createElement("li");
      item.textContent = formatWorkOrderLine(w);
      list.appendChild(item);
    }
    for (const p of s.parts) {
      const item = document.createElement("li");
      item.textContent = `${p.sku} - ${p.name}`;
      list.appendChild(item);
    }
  }
  container.appendChild(list);
  if (!s) {
    const empty = document.createElement("p");
    empty.textContent = "No search results yet.";
    container.appendChild(empty);
  } else if (!s.assets.length && !s.work_orders.length && !s.parts.length) {
    const none = document.createElement("p");
    none.textContent = "No matches.";
    container.appendChild(none);
  }
}

export function renderAuditEvents(container, state, handlers = {}) {
  const list = document.createElement("ul");
  for (const e of state.audit) {
    const item = document.createElement("li");
    item.textContent = `${e.entity_type} / ${e.operation} / ${e.created_at}`;
    list.appendChild(item);
  }
  container.appendChild(list);
  if (state.audit.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No audit events yet.";
    container.appendChild(empty);
  }
}
