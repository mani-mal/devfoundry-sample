import test from "node:test";
import assert from "node:assert/strict";

import {
  PLAN_STATUSES,
  INCIDENT_STATUSES,
  createMaintenanceState,
  setViewer,
  setMaintenanceError,
  clearMaintenanceError,
  setMaintenanceConflict,
  clearMaintenanceConflict,
  canClose,
  formatPlanLine,
  formatIncidentLine,
  formatActionLine,
  renderPlans,
  renderIncidents,
  renderActions,
} from "../../web/js/maintenance.mjs";

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

function makePlan(overrides = {}) {
  return {
    id: "mpl-1",
    name: "Monthly check",
    interval_days: 30,
    horizon_days: 180,
    active: 1,
    ...overrides,
  };
}

function makeIncident(overrides = {}) {
  return {
    id: "inc-1",
    reported_by: "user-111",
    status: "open",
    severity: "high",
    ...overrides,
  };
}

function makeAction(overrides = {}) {
  return {
    id: "act-1",
    required: 1,
    status: "open",
    ...overrides,
  };
}

test("createMaintenanceState returns the empty shape with no storage field", () => {
  const state = createMaintenanceState();
  assert.deepEqual(state, {
    plans: [],
    incidents: [],
    actions: [],
    viewerId: null,
    error: null,
    conflict: null,
  });
  assert.equal(Object.hasOwn(state, "localStorage"), false);
  assert.equal(Object.hasOwn(state, "sessionStorage"), false);
});

test("PLAN_STATUSES and INCIDENT_STATUSES list the expected states", () => {
  assert.deepEqual([...PLAN_STATUSES], ["active", "archived"]);
  assert.deepEqual([...INCIDENT_STATUSES], ["open", "investigating", "closed"]);
  assert.equal(PLAN_STATUSES.length, 2);
  assert.equal(INCIDENT_STATUSES.length, 3);
});

test("setViewer updates the viewer without mutating the input", () => {
  const state = createMaintenanceState();
  const next = setViewer(state, "user-222");
  assert.equal(next.viewerId, "user-222");
  assert.equal(state.viewerId, null);
  assert.deepEqual(state, createMaintenanceState());
});

test("canClose requires a viewer on an exactly open incident", () => {
  const incident = makeIncident();

  for (const status of ["open", "investigating", "closed"]) {
    const current = makeIncident({ status });
    const state = setViewer(createMaintenanceState(), "user-222");
    assert.equal(canClose(state, current), status === "open", `status ${status}`);
  }

  const noViewerState = createMaintenanceState();
  assert.equal(canClose(noViewerState, incident), false);

  const viewerState = setViewer(createMaintenanceState(), "user-222");
  assert.equal(canClose(viewerState, incident), true);
});

test("formatters show ids, severities, and day counts", () => {
  const planLine = formatPlanLine(makePlan());
  assert.match(planLine, /mpl-1/);
  assert.match(planLine, /Monthly check/);
  assert.match(planLine, /30 day\(s\)/);

  const incidentLine = formatIncidentLine(makeIncident());
  assert.match(incidentLine, /inc-1/);
  assert.match(incidentLine, /high/);
  assert.match(incidentLine, /open/);

  const requiredLine = formatActionLine(makeAction());
  assert.match(requiredLine, /act-1/);
  assert.match(requiredLine, /open/);
  assert.match(requiredLine, /required/);

  const optionalLine = formatActionLine(makeAction({ required: 0 }));
  assert.doesNotMatch(optionalLine, /required/);
});

test("renderIncidents toggles the close button with the viewer and never writes innerHTML", () => {
  const openIncident = makeIncident();

  const noViewerContainer = makeStubElement("DIV");
  const noViewerState = { ...createMaintenanceState(), incidents: [openIncident] };
  withDocument(() => renderIncidents(noViewerContainer, noViewerState, { onClose: () => {} }));
  const noViewerItem = noViewerContainer.children[0].children[0];
  assert.deepEqual(noViewerItem.children, []);
  for (const node of [noViewerContainer, noViewerContainer.children[0]]) {
    assert.equal(node.innerHTML_written ?? "", "");
  }

  const viewerContainer = makeStubElement("DIV");
  const viewerState = {
    ...createMaintenanceState(),
    viewerId: "user-222",
    incidents: [openIncident],
  };
  let closed = null;
  withDocument(() =>
    renderIncidents(viewerContainer, viewerState, {
      onClose: (id) => {
        closed = id;
      },
    })
  );
  const button = viewerContainer.children[0].children[0].children[0];
  assert.match(button.textContent, /^Close inc-1$/);
  button.listeners["click"]();
  assert.equal(closed, "inc-1");
  for (const node of [viewerContainer, viewerContainer.children[0]]) {
    assert.equal(node.innerHTML_written ?? "", "");
  }
});

test("renderPlans, renderIncidents, and renderActions build the empty message as the second child", () => {
  const plansContainer = makeStubElement("DIV");
  withDocument(() => renderPlans(plansContainer, createMaintenanceState(), {}));
  assert.equal(plansContainer.children.length, 2);
  assert.equal(plansContainer.children[0].tagName, "ul");
  assert.equal(plansContainer.children[0].children.length, 0);
  assert.equal(plansContainer.children[1].tagName, "p");
  assert.equal(plansContainer.children[1].textContent, "No maintenance plans yet.");

  const incidentsContainer = makeStubElement("DIV");
  withDocument(() => renderIncidents(incidentsContainer, createMaintenanceState(), {}));
  assert.equal(incidentsContainer.children.length, 2);
  assert.equal(incidentsContainer.children[0].tagName, "ul");
  assert.equal(incidentsContainer.children[0].children.length, 0);
  assert.equal(incidentsContainer.children[1].tagName, "p");
  assert.equal(incidentsContainer.children[1].textContent, "No incidents yet.");

  const actionsContainer = makeStubElement("DIV");
  withDocument(() => renderActions(actionsContainer, createMaintenanceState(), {}));
  assert.equal(actionsContainer.children.length, 2);
  assert.equal(actionsContainer.children[0].tagName, "ul");
  assert.equal(actionsContainer.children[0].children.length, 0);
  assert.equal(actionsContainer.children[1].tagName, "p");
  assert.equal(actionsContainer.children[1].textContent, "No corrective actions yet.");
});

test("error and conflict setters are separate and clearable", () => {
  let state = setMaintenanceConflict(createMaintenanceState(), "stale");
  assert.equal(state.conflict, "stale");
  assert.equal(state.error, null);

  state = setMaintenanceError(state, "boom");
  assert.equal(state.error, "boom");
  assert.equal(state.conflict, "stale");

  state = clearMaintenanceConflict(state);
  assert.equal(state.conflict, null);
  assert.equal(state.error, "boom");

  state = clearMaintenanceError(state);
  assert.equal(state.error, null);
});
