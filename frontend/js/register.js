import { register } from "./api.js";
import { formData, showError, hideError } from "./ui.js";

const form = document.getElementById("register-form");
const errorBox = document.getElementById("error");
const successBox = document.getElementById("success");
const submit = document.getElementById("submit");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideError(errorBox);
  successBox.hidden = true;

  submit.disabled = true;
  submit.textContent = "Creating...";

  try {
    await register(formData(form));

    successBox.textContent = "Account created. Redirecting to sign in...";
    successBox.hidden = false;
    form.reset();
    setTimeout(() => (window.location.href = "index.html"), 1500);
  } catch (err) {
    showError(errorBox, err.readable || "Could not create the account.");
    submit.disabled = false;
    submit.textContent = "Create account";
  }
});
