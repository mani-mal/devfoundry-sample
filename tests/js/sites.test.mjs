import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  createSitesState,
  beginSiteForm,
  beginAssetForm,
  setFormValue,
  setFormError,
  clearFormError,
  cancelForm,
  formValuesSurviveError,
  renderSiteForm,
  renderAssetForm,
  renderSiteList,
  renderAssetList,
} from "../../web/js/sites.mjs";

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

test("createSitesState returns the empty shape with no token/storage field", () => {
  const state = createSitesState();
  assert.deepEqual(state, {
    sites: [],
    assets: [],
    selectedSiteId: null,
    selectedAssetId: null,
    error: null,
    form: null,
  });
  assert.equal("token" in state, false);
  assert.equal("storage" in state, false);
});

test("beginSiteForm/beginAssetForm set the form without mutating the input state and copy values", () => {
  const state = createSitesState();
  const values = { code: "SITE-1", name: "Alpha" };
  const withSiteForm = beginSiteForm(state, "create", values);
  assert.equal(withSiteForm.form.kind, "site");
  assert.equal(withSiteForm.form.mode, "create");
  assert.deepEqual(withSiteForm.form.values, { code: "SITE-1", name: "Alpha" });
  assert.deepEqual(state, createSitesState());
  values.code = "CHANGED";
  assert.equal(withSiteForm.form.values.code, "SITE-1");

  const assetValues = { tag: "PUMP-1", criticality: "high" };
  const withAssetForm = beginAssetForm(state, "edit", assetValues);
  assert.equal(withAssetForm.form.kind, "asset");
  assert.equal(withAssetForm.form.mode, "edit");
  assert.deepEqual(withAssetForm.form.values, { tag: "PUMP-1", criticality: "high" });
  assetValues.tag = "CHANGED";
  assert.equal(withAssetForm.form.values.tag, "PUMP-1");
  assert.equal(withAssetForm.form.error, null);
});

test("setFormValue preserves an existing form error", () => {
  let state = createSitesState();
  state = beginSiteForm(state, "create", { code: "S-1" });
  state = setFormError(state, "Code is required.");
  state = setFormValue(state, "name", "Alpha");
  assert.equal(state.form.error, "Code is required.");
  assert.equal(state.form.values.name, "Alpha");
});

test("formValuesSurviveError: true when values are intact, false when a value was lost", () => {
  let state = createSitesState();
  state = beginSiteForm(state, "create", { code: "S-1", name: "Alpha" });
  state = setFormError(state, "Name is required.");
  assert.equal(formValuesSurviveError(state), true);

  const lost = { code: "S-1", name: null };
  assert.equal(formValuesSurviveError(state, lost), false);
});

test("clearFormError clears the error and cancelForm sets form to null", () => {
  let state = createSitesState();
  state = beginSiteForm(state, "create", { code: "S-1" });
  state = setFormError(state, "Code is required.");
  state = clearFormError(state);
  assert.equal(state.form.error, null);
  state = cancelForm(state);
  assert.equal(state.form, null);
});

test("renderSiteForm builds keyboard-accessible controls with disabled code input in edit mode", () => {
  const document = makeStubDocument();
  const savedDocument = globalThis.document;
  globalThis.document = document;
  try {
    let state = createSitesState();
    state = beginSiteForm(state, "edit", { code: "S-1", name: "Alpha", timezone: "UTC" });
    state = setFormError(state, "Name is required.");
    const container = makeStubElement("div");
    const form = renderSiteForm(container, state, { onSubmit: () => {}, onCancel: () => {} });
    assert.equal(form.tagName, "FORM");
    const [heading, codeLabel, codeInput, nameLabel, nameInput, timezoneLabel, timezoneInput, submitButton, cancelButton, errorRegion] = form.children;
    assert.equal(heading.tagName, "H2");
    assert.equal(heading.textContent, "Edit site");
    assert.equal(codeLabel.tagName, "LABEL");
    assert.equal(codeLabel.htmlFor, "site-code");
    assert.equal(codeInput.tagName, "INPUT");
    assert.equal(codeInput.id, "site-code");
    assert.equal(codeInput.autocomplete, "off");
    assert.equal(nameInput.id, "site-name");
    assert.equal(timezoneInput.id, "site-timezone");
    assert.equal(submitButton.tagName, "BUTTON");
    assert.equal(submitButton.textContent, "Save changes");
    assert.equal(cancelButton.type, "button");
    assert.equal(cancelButton.textContent, "Cancel");
    assert.equal(codeInput.disabled, true);
    assert.equal(nameInput.disabled, undefined);
    assert.equal(codeInput.value, "S-1");
    assert.equal(nameInput.value, "Alpha");
    assert.equal(timezoneInput.value, "UTC");
    assert.equal(errorRegion.attributes.role, "alert");
    assert.equal(errorRegion.attributes["aria-live"], "assertive");
    assert.equal(errorRegion.textContent, "Name is required.");
    for (const element of container.appended) {
      assert.equal(element.innerHTML_written, "");
    }
  } finally {
    globalThis.document = savedDocument;
  }
});

test("renderAssetForm: criticality select options, cost input, and disabled tag in edit mode", () => {
  const document = makeStubDocument();
  const savedDocument = globalThis.document;
  globalThis.document = document;
  try {
    let state = createSitesState();
    state = beginAssetForm(state, "edit", { tag: "PUMP-1", criticality: "high", cost: "12500" });
    const container = makeStubElement("div");
    const form = renderAssetForm(container, state, { onSubmit: () => {}, onCancel: () => {} });
    const [, , tagInput] = form.children;
    assert.equal(tagInput.id, "asset-tag");
    assert.equal(tagInput.disabled, true);
    const select = form.children.find((child) => child.tagName === "SELECT");
    assert.equal(select.id, "asset-criticality");
    assert.deepEqual(select.children.map((option) => option.textContent), ["low", "medium", "high"]);
    const selected = select.children.find((option) => option.selected === true);
    assert.equal(selected.value, "high");
    const costInput = form.children.find((child) => child.id === "asset-cost");
    assert.notEqual(costInput, undefined);
    assert.equal(costInput.type, "number");
    assert.equal(costInput.min, "0");
    assert.equal(costInput.step, "1");
  } finally {
    globalThis.document = savedDocument;
  }
});

test("renderSiteList/renderAssetList: one button per item wired to the handler and empty state paragraph", () => {
  const document = makeStubDocument();
  const savedDocument = globalThis.document;
  globalThis.document = document;
  try {
    const state = createSitesState();
    state.sites.push({ id: "s1", code: "S-1", name: "Alpha" });
    state.assets.push({ id: "a1", tag: "PUMP-1", name: "Main pump" });
    const seen = [];
    const siteContainer = makeStubElement("div");
    renderSiteList(siteContainer, state, { onSelect: (id) => seen.push(`site:${id}`) });
    const siteButtons = [];
    for (const li of siteContainer.appended[0].children) {
      siteButtons.push(li.children[0]);
    }
    for (const button of siteButtons) {
      button.listeners.click();
    }
    assert.deepEqual(seen, ["site:s1"]);

    const assetContainer = makeStubElement("div");
    renderAssetList(assetContainer, state, { onSelect: (id) => seen.push(`asset:${id}`) });
    const assetButton = assetContainer.appended[0].children[0].children[0];
    assetButton.listeners.click();
    assert.deepEqual(seen, ["site:s1", "asset:a1"]);

    const emptyContainer = makeStubElement("div");
    renderSiteList(emptyContainer, createSitesState(), { onSelect: () => {} });
    const emptyParagraph = emptyContainer.appended.find((element) => element.tagName === "P");
    assert.equal(emptyParagraph.textContent, "No sites yet.");
  } finally {
    globalThis.document = savedDocument;
  }
});

test("submit handler: the recorded submit handler receives values read from the inputs", () => {
  const document = makeStubDocument();
  const savedDocument = globalThis.document;
  globalThis.document = document;
  try {
    let state = createSitesState();
    state = beginSiteForm(state, "create", { code: "S-1", name: "Alpha", timezone: "UTC" });
    const container = makeStubElement("div");
    const received = [];
    const form = renderSiteForm(container, state, {
      onSubmit: (values) => received.push(values),
      onCancel: () => {},
    });
    form.listeners.submit({ preventDefault: () => {} });
    assert.deepEqual(received, [{ code: "S-1", name: "Alpha", timezone: "UTC" }]);
  } finally {
    globalThis.document = savedDocument;
  }
});

test("no storage access: module source contains neither localStorage nor sessionStorage and no innerHTML", () => {
  const source = readFileSync(new URL("../../web/js/sites.mjs", import.meta.url), "utf8");
  assert.equal(source.includes("localStorage"), false);
  assert.equal(source.includes("sessionStorage"), false);
  assert.equal(source.includes("innerHTML"), false);
});
