import { api, logout, requireAuth } from "./api.js";
import { esc, formatDate, hideError, relativeTime, showError } from "./ui.js";

const user = requireAuth();
const isStaff = user.role === "AGENT" || user.role === "ADMIN";
const isAdmin = user.role === "ADMIN";

// Reads ?id=3 out of the address bar.
const ticketId = new URLSearchParams(window.location.search).get("id");

const errorBox = document.getElementById("error");
const detail = document.getElementById("detail");
const commentsEl = document.getElementById("comments");
const historyEl = document.getElementById("history");
const commentForm = document.getElementById("comment-form");
const commentSubmit = document.getElementById("comment-submit");

document.getElementById("whoami").innerHTML =
  `<b>${esc(user.email)}</b>${esc(user.role)}`;
document.getElementById("logout").addEventListener("click", logout);

document.getElementById("staff-controls").hidden = !isStaff;
document.getElementById("internal-row").hidden = !isStaff;
document.getElementById("delete-ticket").hidden = !isAdmin;

function renderComments(comments) {
  if (comments.length === 0) {
    commentsEl.innerHTML = '<p class="empty">No replies yet.</p>';
    return;
  }

  commentsEl.innerHTML = comments
    .map(
      (c) => `
      <article class="comment ${c.is_internal ? "internal" : ""}">
        <div class="comment-head">
          <b>${esc(c.author.email)}</b>
          <span>${esc(c.author.role)}</span>
          <span>${formatDate(c.created_at)}</span>
          ${c.is_internal ? '<span class="badge overdue">Internal</span>' : ""}
        </div>
        <div class="comment-body">${esc(c.body)}</div>
      </article>`
    )
    .join("");
}

function renderHistory(changes) {
  if (changes.length === 0) {
    historyEl.innerHTML = '<li>No status changes yet.</li>';
    return;
  }

  historyEl.innerHTML = changes
    .map((change) => {
      const from = change.from_status || "new";
      const who = change.changed_by ? esc(change.changed_by.email) : "system";
      return `<li><b>${esc(from)}</b> &rarr; <b>${esc(change.to_status)}</b>
              by ${who}, ${formatDate(change.created_at)}</li>`;
    })
    .join("");
}

async function loadTicket() {
  hideError(errorBox);

  try {
    const ticket = await api.get(`/api/tickets/${ticketId}/`);

    document.title = `#${ticket.id} ${ticket.title} - Helpdesk`;
    document.getElementById("title").textContent = `#${ticket.id} ${ticket.title}`;
    document.getElementById("description").textContent = ticket.description;

    const badge = document.getElementById("status-badge");
    badge.textContent = ticket.status_display;
    badge.className = `badge s-${ticket.status}`;

    document.getElementById("overdue-badge").hidden = !ticket.is_overdue;

    document.getElementById("created-by").textContent = ticket.created_by.email;
    document.getElementById("assigned-to").textContent =
      ticket.assigned_to ? ticket.assigned_to.email : "Unassigned";
    document.getElementById("priority").textContent = ticket.priority_display;
    document.getElementById("created-at").textContent = formatDate(ticket.created_at);
    document.getElementById("sla-due").textContent =
      `${formatDate(ticket.sla_due_at)} (${relativeTime(ticket.sla_due_at)})`;

    if (isStaff) {
      document.getElementById("set-status").value = ticket.status;
      document.getElementById("set-priority").value = ticket.priority;
    }

    renderComments(ticket.comments);
    renderHistory(ticket.status_changes);

    detail.hidden = false;
  } catch (err) {
    // A customer requesting someone else's ticket gets 404, not 403 - the
    // API never confirms that the ticket exists.
    const message =
      err.status === 404
        ? "That ticket does not exist, or you do not have access to it."
        : err.readable || "Could not load the ticket.";
    showError(errorBox, message);
  }
}

commentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideError(errorBox);

  commentSubmit.disabled = true;
  commentSubmit.textContent = "Posting...";

  const payload = {
    ticket: Number(ticketId),
    body: commentForm.body.value,
  };
  if (isStaff) payload.is_internal = document.getElementById("is_internal").checked;

  try {
    await api.post("/api/comments/", payload);
    commentForm.reset();
    await loadTicket();
  } catch (err) {
    showError(errorBox, err.readable || "Could not post the reply.");
  } finally {
    commentSubmit.disabled = false;
    commentSubmit.textContent = "Post reply";
  }
});

document.getElementById("save-changes")?.addEventListener("click", async () => {
  hideError(errorBox);

  try {
    await api.patch(`/api/tickets/${ticketId}/`, {
      status: document.getElementById("set-status").value,
      priority: document.getElementById("set-priority").value,
    });
    await loadTicket();
  } catch (err) {
    showError(errorBox, err.readable || "Could not save the changes.");
  }
});

document.getElementById("delete-ticket")?.addEventListener("click", async () => {
  if (!confirm("Delete this ticket permanently? Its comments go too.")) return;

  try {
    await api.del(`/api/tickets/${ticketId}/`);
    window.location.href = "tickets.html";
  } catch (err) {
    showError(errorBox, err.readable || "Could not delete the ticket.");
  }
});

loadTicket();
