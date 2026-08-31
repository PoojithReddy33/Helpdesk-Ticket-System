"""Builds the text of each notification.

Kept separate from tasks.py so the wording can be tested without running a
worker, and so tasks.py stays about scheduling rather than content.
"""

from django.conf import settings


def ticket_url(ticket_id):
    return f"{settings.FRONTEND_URL}/ticket.html?id={ticket_id}"


def ticket_created(ticket):
    subject = f"[Ticket #{ticket.pk}] We received your request"
    body = f"""Hello {ticket.created_by.first_name or "there"},

We have logged your support request.

  Ticket:   #{ticket.pk} {ticket.title}
  Priority: {ticket.get_priority_display()}
  Due by:   {ticket.sla_due_at:%d %b %Y, %H:%M} UTC

You can follow it here:
{ticket_url(ticket.pk)}

The Helpdesk Team
"""
    return subject, body


def ticket_assigned(ticket):
    subject = f"[Ticket #{ticket.pk}] Assigned to you"
    body = f"""A ticket has been assigned to you.

  Ticket:   #{ticket.pk} {ticket.title}
  Priority: {ticket.get_priority_display()}
  Raised by: {ticket.created_by.email}
  Due by:   {ticket.sla_due_at:%d %b %Y, %H:%M} UTC

{ticket_url(ticket.pk)}
"""
    return subject, body


def status_changed(ticket, from_status, to_status, actor_email):
    subject = f"[Ticket #{ticket.pk}] Status is now {to_status.replace('_', ' ').title()}"
    body = f"""Your ticket has been updated.

  Ticket: #{ticket.pk} {ticket.title}
  Status: {from_status or "new"} -> {to_status}
  By:     {actor_email}

{ticket_url(ticket.pk)}
"""
    return subject, body


def comment_added(comment):
    subject = f"[Ticket #{comment.ticket_id}] New reply"
    body = f"""{comment.author.email} replied to your ticket.

  Ticket: #{comment.ticket_id} {comment.ticket.title}

  "{comment.body}"

{ticket_url(comment.ticket_id)}
"""
    return subject, body


def sla_breach_digest(tickets):
    subject = f"[Helpdesk] {len(tickets)} ticket(s) past their SLA deadline"

    lines = [
        f"  #{t.pk} {t.title}\n"
        f"      priority={t.get_priority_display()}  "
        f"due={t.sla_due_at:%d %b %H:%M} UTC  "
        f"assigned={t.assigned_to.email if t.assigned_to else 'nobody'}"
        for t in tickets
    ]

    body = "The following tickets are overdue:\n\n" + "\n".join(lines) + "\n"
    return subject, body
