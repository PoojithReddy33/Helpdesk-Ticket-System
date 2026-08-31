import { api, logout, requireAuth } from "./api.js";
import { esc, formData, hideError, relativeTime, showError } from "./ui.js";

const user = requireAuth();

const listEl = document.getElementById("list");
const countEl = document.getElementById("count");
const errorBox = document.getElementById("error");
const createForm = document.getElementById("create-form");
const createSubmit = document.getElementById("create-submit");

const filters = {
  status: document.getElementById("filter-status"),
  priority: document.getElementById("filter-priority"),
  search: document.getElementById("filter-search"),
};

const isStaff = user.role === "AGENT" || user.role === "ADMIN";

document.getElementById("whoami").innerHTML =
  `<b>${esc(user.email)}</b>${esc(user.role)}`;
document.getElementById("logout").addEventListener("click", logout);

// Customers may not choose their own priority - the API rejects it, so the
// control is hidden rather than shown and then failing.
//
// `hidden` only hides the field visually; a hidden input is STILL submitted.
// Disabling it is what actually keeps it out of FormData.
document.getElementById("priority-field").hidden = !isStaff;
document.getElementById("priority").disabled = !isStaff;

/** Builds "?status=OPEN&search=riya" from whatever the user selected. */
function buildQuery() {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, input]) => {
    if (input.value) params.set(key, input.value);
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

function ticketCard(ticket) {
  const overdue = ticket.is_overdue
    ? '<span class="badge overdue">Overdue</span>'
    : "";

  const assignee = ticket.assigned_to
    ? esc(ticket.assigned_to.email)
    : "Unassigned";

  // Every interpolated value passes through esc() first.
  return `
    <button class="ticket p-${esc(ticket.priority)}" data-id="${ticket.id}">
      <div class="ticket-head">
        <span class="ticket-id">#${ticket.id}</span>
        <span class="ticket-title">${esc(ticket.title)}</span>
        <span class="badge s-${esc(ticket.status)}">${esc(ticket.status_display)}</span>
        ${overdue}
      </div>
      <div class="ticket-meta">
        <span>${esc(ticket.priority_display)} priority</span>
        <span>By ${esc(ticket.created_by.email)}</span>
        <span>${assignee}</span>
        <span>Due ${relativeTime(ticket.sla_due_at)}</span>
      </div>
    </button>`;
}

async function loadTickets() {
  hideError(errorBox);
  listEl.innerHTML = '<p class="empty">Loading...</p>';

  try {
    const page = await api.get(`/api/tickets/${buildQuery()}`);

    countEl.textContent =
      page.count === 1 ? "1 ticket" : `${page.count} tickets`;

    if (page.results.length === 0) {
      listEl.innerHTML =
        '<p class="empty">No tickets match. Raise one above, or clear the filters.</p>';
      return;
    }

    listEl.innerHTML = page.results.map(ticketCard).join("");
  } catch (err) {
    listEl.innerHTML = "";
    showError(errorBox, err.readable || "Could not load tickets.");
  }
}

// One listener on the container instead of one per card. New cards added
// later are handled automatically - this is called event delegation.
listEl.addEventListener("click", (event) => {
  const card = event.target.closest(".ticket");
  if (card) window.location.href = `ticket.html?id=${card.dataset.id}`;
});

createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideError(errorBox);

  createSubmit.disabled = true;
  createSubmit.textContent = "Creating...";

  try {
    await api.post("/api/tickets/", formData(createForm));
    createForm.reset();
    await loadTickets();
  } catch (err) {
    showError(errorBox, err.readable || "Could not create the ticket.");
  } finally {
    createSubmit.disabled = false;
    createSubmit.textContent = "Create ticket";
  }
});

// Dropdowns reload immediately; the search box waits until typing pauses.
filters.status.addEventListener("change", loadTickets);
filters.priority.addEventListener("change", loadTickets);

let searchTimer;
filters.search.addEventListener("input", () => {
  // Debounce: reset the timer on every keystroke so only the final pause
  // fires a request, instead of one per character.
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadTickets, 350);
});

document.getElementById("clear-filters").addEventListener("click", () => {
  Object.values(filters).forEach((input) => (input.value = ""));
  loadTickets();
});

loadTickets();
