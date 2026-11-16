// Pure ES module for the maintenance and incident screens: maintenance
// plans, incidents, and corrective actions. No DOM work happens at import
// time; all DOM work happens in the functions the caller invokes (the
// render* functions below). Render functions build controls with
// createElement/textContent ONLY (never raw inner HTML markup with
// dynamic user text). State is in-memory only; the UI consumes domain
// rows snake_case exactly as the server serializes them. The close rule
// lives here in ONE place (canClose) and every render path derives
// through it, so the rule is applied consistently everywhere. Server
// denial (open required actions) is tested separately; here the UI rule
// is the accept core. Error and conflict are separate clearable slots.
// No fetch/API calls; no browser web storage APIs anywhere.

export const PLAN_STATUSES = ["active", "archived"];

export const INCIDENT_STATUSES = ["open", "investigating", "closed"];

export function createMaintenanceState() {
  return {
    plans: [],
    incidents: [],
    actions: [],
    viewerId: null,
    error: null,
    conflict: null,
  };
}

export function setViewer(state, viewerId) {
  return { ...state, viewerId };
}

export function setMaintenanceError(state, message) {
  return { ...state, error: message };
}

export function clearMaintenanceError(state) {
  return { ...state, error: null };
}

export function setMaintenanceConflict(state, message) {
  return { ...state, conflict: message };
}

export function clearMaintenanceConflict(state) {
  return { ...state, conflict: null };
}

// The single source of truth for the UI close hint: only a viewer who is
// set and sees an incident in exactly the "open" status may close. The
// server still enforces open required actions separately; this hint is
// independent of that check.
export function canClose(state, incident) {
  return state.viewerId !== null && incident.status === "open";
}

export function formatPlanLine(plan) {
  return `Maintenance plan ${plan.id}: ${plan.name}, every ${plan.interval_days} day(s), horizon ${plan.horizon_days} days`;
}

export function formatIncidentLine(incident) {
  return `Incident ${incident.id}: severity ${incident.severity}, status ${incident.status}`;
}

export function formatActionLine(action) {
  const label = action.required ? "required" : "optional";
  return `Corrective action ${action.id}: status ${action.status}, ${label}`;
}

export function renderPlans(container, state, handlers = {}) {
  const list = document.createElement("ul");
  for (const plan of state.plans) {
    const item = document.createElement("li");
    item.textContent = formatPlanLine(plan);
    list.appendChild(item);
  }
  container.appendChild(list);
  if (state.plans.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No maintenance plans yet.";
    container.appendChild(empty);
  }
}

export function renderIncidents(container, state, handlers = {}) {
  const list = document.createElement("ul");
  for (const incident of state.incidents) {
    const item = document.createElement("li");
    item.textContent = formatIncidentLine(incident);
    if (canClose(state, incident)) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `Close ${incident.id}`;
      button.addEventListener("click", () => {
        handlers.onClose(incident.id);
      });
      item.appendChild(button);
    }
    list.appendChild(item);
  }
  container.appendChild(list);
  if (state.incidents.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No incidents yet.";
    container.appendChild(empty);
  }
}

export function renderActions(container, state, handlers = {}) {
  const list = document.createElement("ul");
  for (const action of state.actions) {
    const item = document.createElement("li");
    item.textContent = formatActionLine(action);
    list.appendChild(item);
  }
  container.appendChild(list);
  if (state.actions.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No corrective actions yet.";
    container.appendChild(empty);
  }
}
