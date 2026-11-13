import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  createAuthState,
  loginMessage,
  applyLoginResult,
  applyLogout,
  renderLogin,
  renderAccount,
  loginErrorFor,
} from "../../web/js/auth.mjs";

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

test("createAuthState returns the anonymous shape with no token field", () => {
  const state = createAuthState();
  assert.deepEqual(state, { status: "anonymous", userEmail: null, error: null });
  assert.equal("token" in state, false);
});

test("applyLoginResult ok path authenticates with email and does not mutate input", () => {
  const state = createAuthState();
  const result = applyLoginResult(state, { ok: true, email: "user@example.com" });
  assert.equal(result.status, "authenticated");
  assert.equal(result.userEmail, "user@example.com");
  assert.equal(result.error, null);
  assert.deepEqual(state, { status: "anonymous", userEmail: null, error: null });
});

test("applyLoginResult failure path stays anonymous with error set", () => {
  const state = createAuthState();
  const result = applyLoginResult(state, { ok: false, message: "Email or password is wrong." });
  assert.equal(result.status, "anonymous");
  assert.equal(result.userEmail, null);
  assert.equal(result.error, "Email or password is wrong.");
});

test("applyLogout returns a new anonymous state with no error", () => {
  const authenticated = { status: "authenticated", userEmail: "user@example.com", error: null };
  const state = applyLogout(authenticated);
  assert.deepEqual(state, { status: "anonymous", userEmail: null, error: null });
  assert.deepEqual(authenticated, { status: "authenticated", userEmail: "user@example.com", error: null });
});

test("loginMessage returns empty string when no error and the error text when set", () => {
  assert.equal(loginMessage(createAuthState()), "");
  assert.equal(loginMessage({ status: "anonymous", userEmail: null, error: "Sign-in failed. Try again." }), "Sign-in failed. Try again.");
});

test("loginErrorFor maps 401 and 403 distinctly and everything else generically", () => {
  assert.equal(loginErrorFor(401), "Email or password is wrong.");
  assert.equal(loginErrorFor(403), "You do not have access to this site.");
  assert.equal(loginErrorFor(500), "Sign-in failed. Try again.");
  assert.equal(loginErrorFor(undefined), "Sign-in failed. Try again.");
});

test("renderLogin builds the form with labels, inputs, button, and alert region", () => {
  const document = makeStubDocument();
  const container = makeStubElement("div");
  const savedDocument = globalThis.document;
  globalThis.document = document;
  try {
    const form = renderLogin(container, createAuthState(), { onLogin: () => {} });
    assert.equal(form.tagName, "FORM");
    const [heading, emailLabel, emailInput, passwordLabel, passwordInput, button, errorRegion] = form.children;
    assert.equal(heading.tagName, "H2");
    assert.equal(heading.textContent, "Sign in");
    assert.equal(passwordLabel.tagName, "LABEL");
    assert.equal(passwordLabel.textContent, "Password");
    assert.equal(passwordInput.tagName, "INPUT");
    assert.equal(passwordInput.type, "password");
    assert.equal(passwordInput.required, true);
    assert.equal(button.tagName, "BUTTON");
    assert.equal(button.textContent, "Sign in");
    assert.equal(errorRegion.attributes.role, "alert");
    assert.equal(errorRegion.attributes["aria-live"], "assertive");
    assert.equal(errorRegion.textContent, "");
    const emailFields = form.children.filter((child) => child.tagName === "LABEL");
    assert.equal(emailFields.length, 2);
    const labels = form.children.filter((child) => child.tagName === "LABEL");
    assert.equal(labels[0].htmlFor, "login-email");
    assert.equal(labels[1].htmlFor, "login-password");
    const inputs = form.children.filter((child) => child.tagName === "INPUT");
    assert.equal(inputs.length, 2);
    assert.equal(inputs[0].id, "login-email");
    assert.equal(inputs[0].type, "email");
    assert.equal(inputs[1].id, "login-password");
    assert.equal(inputs[1].type, "password");
  } finally {
    globalThis.document = savedDocument;
  }
  for (const element of container.appended) {
    assert.equal(element.innerHTML_written, "");
  }
});

test("no storage access: module source contains neither localStorage nor sessionStorage", () => {
  const source = readFileSync(new URL("../../web/js/auth.mjs", import.meta.url), "utf8");
  assert.equal(source.includes("localStorage"), false);
  assert.equal(source.includes("sessionStorage"), false);
});
