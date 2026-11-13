// Pure ES module for site/asset list, detail, and edit UI logic.
// No DOM work happens at import time; all DOM work happens in the
// functions the caller invokes (the render* functions below). Render
// functions build controls with createElement/textContent ONLY (never
// raw inner HTML markup with dynamic user text) and use real
// button/input/select
// elements, so every control is keyboard-reachable by default (no
// div onClick handlers, no tab-index hacks). Input values are always
// re-rendered from state on every pass, so errors never destroy typed
// values ("errors preserve values"). No fetch/API calls here; no
// browser web storage APIs anywhere (state is in-memory only).

export function createSitesState() {
  return {
    sites: [],
    assets: [],
    selectedSiteId: null,
    selectedAssetId: null,
    error: null,
    form: null,
  };
}

export function beginSiteForm(state, mode, values = {}) {
  return {
    ...state,
    form: { kind: "site", mode, values: { ...values }, error: null },
  };
}

export function beginAssetForm(state, mode, values = {}) {
  return {
    ...state,
    form: { kind: "asset", mode, values: { ...values }, error: null },
  };
}

export function setFormValue(state, field, value) {
  return {
    ...state,
    form: {
      ...state.form,
      values: { ...state.form.values, [field]: value },
    },
  };
}

export function setFormError(state, message) {
  return {
    ...state,
    form: { ...state.form, error: message },
  };
}

export function clearFormError(state) {
  return {
    ...state,
    form: { ...state.form, error: null },
  };
}

export function cancelForm(state) {
  return { ...state, form: null };
}

export function formValuesSurviveError(state, snapshot = null) {
  if (!state.form) {
    return false;
  }
  const expected = snapshot ?? state.form.values;
  return Object.keys(expected).every(
    (key) => state.form.values[key] === expected[key],
  );
}

export function renderSiteForm(container, state, handlers) {
  const form = document.createElement("form");
  const heading = document.createElement("h2");
  heading.textContent = state.form.mode === "edit" ? "Edit site" : "Create site";
  form.appendChild(heading);

  const codeLabel = document.createElement("label");
  codeLabel.htmlFor = "site-code";
  codeLabel.textContent = "Code";
  form.appendChild(codeLabel);

  const codeInput = document.createElement("input");
  codeInput.type = "text";
  codeInput.id = "site-code";
  codeInput.autocomplete = "off";
  codeInput.value = state.form.values.code ?? "";
  codeInput.disabled = state.form.mode === "edit";
  form.appendChild(codeInput);

  const nameLabel = document.createElement("label");
  nameLabel.htmlFor = "site-name";
  nameLabel.textContent = "Name";
  form.appendChild(nameLabel);

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.id = "site-name";
  nameInput.value = state.form.values.name ?? "";
  form.appendChild(nameInput);

  const timezoneLabel = document.createElement("label");
  timezoneLabel.htmlFor = "site-timezone";
  timezoneLabel.textContent = "Timezone";
  form.appendChild(timezoneLabel);

  const timezoneInput = document.createElement("input");
  timezoneInput.type = "text";
  timezoneInput.id = "site-timezone";
  timezoneInput.value = state.form.values.timezone ?? "";
  form.appendChild(timezoneInput);

  const submit = document.createElement("button");
  submit.textContent = state.form.mode === "edit" ? "Save changes" : "Create site";
  form.appendChild(submit);

  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", () => {
    handlers.onCancel();
  });
  form.appendChild(cancel);

  const error = document.createElement("p");
  error.setAttribute("role", "alert");
  error.setAttribute("aria-live", "assertive");
  error.textContent = state.form.error ?? "";
  form.appendChild(error);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    handlers.onSubmit({
      code: codeInput.value,
      name: nameInput.value,
      timezone: timezoneInput.value,
    });
  });

  container.appendChild(form);
  return form;
}

export function renderAssetForm(container, state, handlers) {
  const form = document.createElement("form");
  const heading = document.createElement("h2");
  heading.textContent = state.form.mode === "edit" ? "Edit asset" : "Create asset";
  form.appendChild(heading);

  const tagLabel = document.createElement("label");
  tagLabel.htmlFor = "asset-tag";
  tagLabel.textContent = "Tag";
  form.appendChild(tagLabel);

  const tagInput = document.createElement("input");
  tagInput.type = "text";
  tagInput.id = "asset-tag";
  tagInput.autocomplete = "off";
  tagInput.value = state.form.values.tag ?? "";
  tagInput.disabled = state.form.mode === "edit";
  form.appendChild(tagInput);

  const nameLabel = document.createElement("label");
  nameLabel.htmlFor = "asset-name";
  nameLabel.textContent = "Name";
  form.appendChild(nameLabel);

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.id = "asset-name";
  nameInput.value = state.form.values.name ?? "";
  form.appendChild(nameInput);

  const criticalityLabel = document.createElement("label");
  criticalityLabel.htmlFor = "asset-criticality";
  criticalityLabel.textContent = "Criticality";
  form.appendChild(criticalityLabel);

  const criticalitySelect = document.createElement("select");
  criticalitySelect.id = "asset-criticality";
  for (const level of ["low", "medium", "high"]) {
    const option = document.createElement("option");
    option.textContent = level;
    option.value = level;
    if (state.form.values.criticality === level) {
      option.selected = true;
    }
    criticalitySelect.appendChild(option);
  }
  form.appendChild(criticalitySelect);

  const costLabel = document.createElement("label");
  costLabel.htmlFor = "asset-cost";
  costLabel.textContent = "Purchase cost (cents)";
  form.appendChild(costLabel);

  const costInput = document.createElement("input");
  costInput.type = "number";
  costInput.id = "asset-cost";
  costInput.min = "0";
  costInput.step = "1";
  costInput.value = state.form.values.cost ?? "";
  form.appendChild(costInput);

  const submit = document.createElement("button");
  submit.textContent = state.form.mode === "edit" ? "Save changes" : "Create asset";
  form.appendChild(submit);

  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", () => {
    handlers.onCancel();
  });
  form.appendChild(cancel);

  const error = document.createElement("p");
  error.setAttribute("role", "alert");
  error.setAttribute("aria-live", "assertive");
  error.textContent = state.form.error ?? "";
  form.appendChild(error);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    handlers.onSubmit({
      tag: tagInput.value,
      name: nameInput.value,
      criticality: criticalitySelect.value,
      cost: Number(costInput.value),
    });
  });

  container.appendChild(form);
  return form;
}

export function renderSiteList(container, state, handlers) {
  const list = document.createElement("ul");
  for (const site of state.sites) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${site.code} — ${site.name}`;
    button.addEventListener("click", () => {
      handlers.onSelect(site.id);
    });
    item.appendChild(button);
    list.appendChild(item);
  }
  container.appendChild(list);
  if (state.sites.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No sites yet.";
    container.appendChild(empty);
  }
}

export function renderAssetList(container, state, handlers) {
  const list = document.createElement("ul");
  for (const asset of state.assets) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${asset.tag} — ${asset.name}`;
    button.addEventListener("click", () => {
      handlers.onSelect(asset.id);
    });
    item.appendChild(button);
    list.appendChild(item);
  }
  container.appendChild(list);
  if (state.assets.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No assets yet.";
    container.appendChild(empty);
  }
}
