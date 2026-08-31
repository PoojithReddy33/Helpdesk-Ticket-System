import { login, tokens } from "./api.js";
import { showError, hideError } from "./ui.js";

const form = document.getElementById("login-form");
const errorBox = document.getElementById("error");
const submit = document.getElementById("submit");

// Already signed in? Skip the form.
if (tokens.access) window.location.href = "tickets.html";

form.addEventListener("submit", async (event) => {
  // Stop the browser's default full-page form POST - we send JSON instead.
  event.preventDefault();
  hideError(errorBox);

  submit.disabled = true;
  submit.textContent = "Signing in...";

  try {
    await login(form.email.value, form.password.value);
    window.location.href = "tickets.html";
  } catch (err) {
    showError(errorBox, err.readable || "Could not sign in.");
    submit.disabled = false;
    submit.textContent = "Sign in";
  }
});
