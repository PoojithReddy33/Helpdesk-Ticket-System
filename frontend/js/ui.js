/** Small helpers shared by every page. */

/**
 * Escapes text before it goes into innerHTML.
 *
 * Without this, a ticket titled <img src=x onerror=alert(1)> would execute
 * in every viewer's browser - a stored XSS vulnerability.
 */
export function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/** UTC from the API rendered in whatever timezone the viewer is in. */
export function formatDate(iso) {
  if (!iso) return "--";
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/** "in 3 hours" / "2 days ago", derived from the same UTC string. */
export function relativeTime(iso) {
  if (!iso) return "--";

  const diffMs = new Date(iso) - new Date();
  const units = [
    ["day", 86400000],
    ["hour", 3600000],
    ["minute", 60000],
  ];
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

  for (const [unit, ms] of units) {
    if (Math.abs(diffMs) >= ms || unit === "minute") {
      return formatter.format(Math.round(diffMs / ms), unit);
    }
  }
  return "now";
}

export function showError(element, message) {
  element.textContent = message;
  element.hidden = false;
}

export function hideError(element) {
  element.hidden = true;
}

/** Turns a <form> into a plain object, dropping empty optional values. */
export function formData(form) {
  const result = {};
  new FormData(form).forEach((value, key) => {
    if (value !== "") result[key] = value;
  });
  return result;
}
