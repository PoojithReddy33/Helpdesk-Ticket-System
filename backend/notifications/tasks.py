"""Work that runs OUTSIDE the request/response cycle.

Every function here is called through django_q's async_task(), so the HTTP
response returns immediately and a worker process does the slow part.

Each task takes ids, never model instances - see the note in
notify_ticket_created for why that matters.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from accounts.models import User
from tickets.models import Comment, Ticket

from . import emails

logger = logging.getLogger(__name__)


def _send(subject, body, recipients):
    """One place where mail actually leaves. Never raises into the worker."""
    recipients = [r for r in recipients if r]
    if not recipients:
        return 0

    sent = send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
        fail_silently=False,
    )
    logger.info("Sent %r to %s", subject, ", ".join(recipients))
    return sent


def notify_ticket_created(ticket_id):
    """Confirm to the customer, and alert the assigned agent if there is one.

    Takes an id rather than a Ticket because the task is serialised into the
    database and may run seconds later - by which time a pickled instance
    would be stale. Re-reading guarantees current data.
    """
    ticket = Ticket.objects.select_related("created_by", "assigned_to").get(pk=ticket_id)

    subject, body = emails.ticket_created(ticket)
    _send(subject, body, [ticket.created_by.email])

    if ticket.assigned_to:
        subject, body = emails.ticket_assigned(ticket)
        _send(subject, body, [ticket.assigned_to.email])

    return f"notified for ticket {ticket_id}"


def notify_status_changed(ticket_id, from_status, to_status, actor_id):
    ticket = Ticket.objects.select_related("created_by").get(pk=ticket_id)
    actor = User.objects.filter(pk=actor_id).first()

    subject, body = emails.status_changed(
        ticket, from_status, to_status, actor.email if actor else "the system"
    )
    _send(subject, body, [ticket.created_by.email])

    return f"status notification sent for ticket {ticket_id}"


def notify_comment_added(comment_id):
    """Tell the other side there is a reply.

    Internal notes are never emailed to the customer - the same rule the
    serializer enforces on read, applied here on send.
    """
    comment = Comment.objects.select_related(
        "author", "ticket", "ticket__created_by", "ticket__assigned_to"
    ).get(pk=comment_id)

    if comment.is_internal:
        # Staff-only note: tell the assigned agent, never the customer.
        agent = comment.ticket.assigned_to
        if agent and agent.pk != comment.author_id:
            subject, body = emails.comment_added(comment)
            _send(subject, body, [agent.email])
        return f"internal note {comment_id}: customer not notified"

    ticket = comment.ticket
    if comment.author_id == ticket.created_by_id:
        # Customer replied -> tell the agent.
        recipients = [ticket.assigned_to.email] if ticket.assigned_to else []
    else:
        # Staff replied -> tell the customer.
        recipients = [ticket.created_by.email]

    subject, body = emails.comment_added(comment)
    _send(subject, body, recipients)

    return f"comment notification sent for comment {comment_id}"


def check_sla_breaches():
    """Scheduled sweep: email admins about tickets past their deadline.

    Runs on a schedule rather than being triggered by a request, because
    nothing happens at the moment a deadline passes - there is no request
    to hook into.
    """
    overdue = (
        Ticket.objects.select_related("assigned_to")
        .filter(
            sla_due_at__lt=timezone.now(),
            status__in=[Ticket.Status.OPEN, Ticket.Status.IN_PROGRESS],
        )
        .order_by("sla_due_at")
    )

    if not overdue.exists():
        return "no breaches"

    tickets = list(overdue)
    admin_emails = list(
        User.objects.filter(role=User.Role.ADMIN, is_active=True).values_list(
            "email", flat=True
        )
    )

    subject, body = emails.sla_breach_digest(tickets)
    _send(subject, body, admin_emails)

    return f"reported {len(tickets)} breached ticket(s)"
