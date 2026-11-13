export function createAuthState() {
  return { status: "anonymous", userEmail: null, error: null };
}

export function applyLoginResult(state, result) {
  if (result.ok) {
    return { status: "authenticated", userEmail: result.email, error: null };
  }
  return { status: "anonymous", userEmail: null, error: result.message };
}

export function loginMessage(state) {
  return state.error ?? "";
}

export function applyLogout(state) {
  return createAuthState();
}

export function renderLogin(container, state, handlers) {
  const form = document.createElement("form");
  const heading = document.createElement("h2");
  heading.textContent = "Sign in";
  form.appendChild(heading);

  const emailLabel = document.createElement("label");
  emailLabel.htmlFor = "login-email";
  emailLabel.textContent = "Email";
  form.appendChild(emailLabel);

  const emailInput = document.createElement("input");
  emailInput.type = "email";
  emailInput.id = "login-email";
  emailInput.required = true;
  emailInput.autocomplete = "username";
  form.appendChild(emailInput);

  const passwordLabel = document.createElement("label");
  passwordLabel.htmlFor = "login-password";
  passwordLabel.textContent = "Password";
  form.appendChild(passwordLabel);

  const passwordInput = document.createElement("input");
  passwordInput.type = "password";
  passwordInput.id = "login-password";
  passwordInput.required = true;
  passwordInput.autocomplete = "current-password";
  form.appendChild(passwordInput);

  const button = document.createElement("button");
  button.textContent = "Sign in";
  form.appendChild(button);

  const error = document.createElement("p");
  error.setAttribute("role", "alert");
  error.setAttribute("aria-live", "assertive");
  error.textContent = loginMessage(state);
  form.appendChild(error);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    handlers.onLogin({ email: emailInput.value, password: passwordInput.value });
  });

  container.appendChild(form);
  return form;
}

export function renderAccount(container, state, handlers) {
  if (state.status !== "authenticated") {
    return;
  }
  const status = document.createElement("p");
  status.textContent = `Signed in as ${state.userEmail}`;
  container.appendChild(status);

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Sign out";
  button.addEventListener("click", () => {
    handlers.onLogout();
  });
  container.appendChild(button);
}

export function loginErrorFor(status) {
  if (status === 401) {
    return "Email or password is wrong.";
  }
  if (status === 403) {
    return "You do not have access to this site.";
  }
  return "Sign-in failed. Try again.";
}
