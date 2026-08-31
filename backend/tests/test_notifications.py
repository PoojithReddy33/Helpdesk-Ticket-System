"""Background notification tasks, and the enqueueing that triggers them."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.utils import timezone

from notifications.tasks import (
    check_sla_breaches,
    notify_comment_added,
    notify_status_changed,
    notify_ticket_created,
)
from tickets.models import Ticket

from .factories import AdminFactory, CommentFactory, TicketFactory

pytestmark = pytest.mark.django_db


class TestTicketCreatedEmail:
    def test_the_customer_is_confirmed(self, customer):
        ticket = TicketFactory(created_by=customer)
        mail.outbox.clear()

        notify_ticket_created(ticket.pk)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [customer.email]
        assert f"#{ticket.pk}" in mail.outbox[0].subject

    def test_the_assigned_agent_is_alerted_too(self, customer, agent):
        ticket = TicketFactory(created_by=customer, assigned_to=agent)
        mail.outbox.clear()

        notify_ticket_created(ticket.pk)

        recipients = [address for message in mail.outbox for address in message.to]
        assert customer.email in recipients
        assert agent.email in recipients

    def test_an_unassigned_ticket_emails_only_the_customer(self, customer):
        ticket = TicketFactory(created_by=customer, assigned_to=None)
        mail.outbox.clear()

        notify_ticket_created(ticket.pk)

        assert len(mail.outbox) == 1

    def test_the_email_links_back_to_the_ticket(self, customer, settings):
        ticket = TicketFactory(created_by=customer)
        mail.outbox.clear()

        notify_ticket_created(ticket.pk)

        expected = f"{settings.FRONTEND_URL}/ticket.html?id={ticket.pk}"
        assert expected in mail.outbox[0].body


class TestStatusChangeEmail:
    def test_the_customer_is_told_who_changed_it(self, customer, agent):
        ticket = TicketFactory(created_by=customer, status=Ticket.Status.OPEN)
        mail.outbox.clear()

        notify_status_changed(ticket.pk, "OPEN", "IN_PROGRESS", agent.pk)

        assert mail.outbox[0].to == [customer.email]
        assert agent.email in mail.outbox[0].body

    def test_a_deleted_actor_does_not_break_the_task(self, customer):
        """changed_by uses SET_NULL, so the actor may be gone by send time."""
        ticket = TicketFactory(created_by=customer)
        mail.outbox.clear()

        notify_status_changed(ticket.pk, "OPEN", "CLOSED", 999999)

        assert len(mail.outbox) == 1
        assert "the system" in mail.outbox[0].body


class TestCommentEmail:
    def test_an_internal_note_never_reaches_the_customer(self, customer, agent):
        ticket = TicketFactory(created_by=customer, assigned_to=agent)
        note = CommentFactory(ticket=ticket, author=agent, is_internal=True)
        mail.outbox.clear()

        notify_comment_added(note.pk)

        recipients = [address for message in mail.outbox for address in message.to]
        assert customer.email not in recipients

    def test_a_public_staff_reply_reaches_the_customer(self, customer, agent):
        ticket = TicketFactory(created_by=customer, assigned_to=agent)
        reply = CommentFactory(ticket=ticket, author=agent, is_internal=False)
        mail.outbox.clear()

        notify_comment_added(reply.pk)

        assert mail.outbox[0].to == [customer.email]

    def test_a_customer_reply_reaches_the_assigned_agent(self, customer, agent):
        ticket = TicketFactory(created_by=customer, assigned_to=agent)
        reply = CommentFactory(ticket=ticket, author=customer)
        mail.outbox.clear()

        notify_comment_added(reply.pk)

        assert mail.outbox[0].to == [agent.email]

    def test_a_customer_reply_on_an_unassigned_ticket_emails_nobody(self, customer):
        ticket = TicketFactory(created_by=customer, assigned_to=None)
        reply = CommentFactory(ticket=ticket, author=customer)
        mail.outbox.clear()

        notify_comment_added(reply.pk)

        assert len(mail.outbox) == 0


class TestSlaSweep:
    def test_nothing_overdue_sends_nothing(self, customer):
        TicketFactory(created_by=customer)
        mail.outbox.clear()

        assert check_sla_breaches() == "no breaches"
        assert len(mail.outbox) == 0

    def test_overdue_tickets_are_reported_to_admins(self, customer):
        admin = AdminFactory()
        ticket = TicketFactory(created_by=customer, status=Ticket.Status.OPEN)
        # .update() bypasses save(), so the deadline is not recalculated.
        Ticket.objects.filter(pk=ticket.pk).update(
            sla_due_at=timezone.now() - timedelta(hours=3)
        )
        mail.outbox.clear()

        result = check_sla_breaches()

        assert "1 breached" in result
        assert mail.outbox[0].to == [admin.email]
        assert f"#{ticket.pk}" in mail.outbox[0].body

    @pytest.mark.parametrize("status", [Ticket.Status.RESOLVED, Ticket.Status.CLOSED])
    def test_finished_tickets_are_not_chased(self, customer, status):
        AdminFactory()
        ticket = TicketFactory(created_by=customer, status=status)
        Ticket.objects.filter(pk=ticket.pk).update(
            sla_due_at=timezone.now() - timedelta(days=2)
        )
        mail.outbox.clear()

        assert check_sla_breaches() == "no breaches"


class TestEnqueueing:
    """The view should hand work off, not do it inline."""

    def test_creating_a_ticket_enqueues_a_notification(
        self, as_user, customer, django_capture_on_commit_callbacks
    ):
        with patch("tickets.views.async_task") as enqueue:
            # on_commit callbacks do not run inside a test transaction unless
            # they are explicitly captured and executed.
            with django_capture_on_commit_callbacks(execute=True):
                response = as_user(customer).post(
                    "/api/tickets/",
                    {"title": "Printer offline", "description": "No response."},
                    format="json",
                )

        assert response.status_code == 201
        enqueue.assert_called_once()
        assert enqueue.call_args[0][0] == "notifications.tasks.notify_ticket_created"

    def test_a_status_change_enqueues_a_notification(
        self, as_user, agent, customer, django_capture_on_commit_callbacks
    ):
        ticket = TicketFactory(created_by=customer, status=Ticket.Status.OPEN)

        with patch("tickets.views.async_task") as enqueue:
            with django_capture_on_commit_callbacks(execute=True):
                as_user(agent).patch(
                    f"/api/tickets/{ticket.pk}/",
                    {"status": Ticket.Status.IN_PROGRESS},
                    format="json",
                )

        assert enqueue.call_args[0][0] == "notifications.tasks.notify_status_changed"

    def test_editing_a_title_enqueues_nothing(
        self, as_user, agent, customer, django_capture_on_commit_callbacks
    ):
        ticket = TicketFactory(created_by=customer)

        with patch("tickets.views.async_task") as enqueue:
            with django_capture_on_commit_callbacks(execute=True):
                as_user(agent).patch(
                    f"/api/tickets/{ticket.pk}/", {"title": "Renamed"}, format="json"
                )

        enqueue.assert_not_called()

    def test_posting_a_comment_enqueues_a_notification(
        self, as_user, customer, django_capture_on_commit_callbacks
    ):
        ticket = TicketFactory(created_by=customer)

        with patch("tickets.views.async_task") as enqueue:
            with django_capture_on_commit_callbacks(execute=True):
                as_user(customer).post(
                    "/api/comments/",
                    {"ticket": ticket.pk, "body": "Any update?"},
                    format="json",
                )

        assert enqueue.call_args[0][0] == "notifications.tasks.notify_comment_added"


class TestInternalNoteRouting:
    def test_an_internal_note_alerts_the_assigned_agent(self, customer, agent, admin):
        """Written by an admin, so the assigned agent still needs telling."""
        ticket = TicketFactory(created_by=customer, assigned_to=agent)
        note = CommentFactory(ticket=ticket, author=admin, is_internal=True)
        mail.outbox.clear()

        notify_comment_added(note.pk)

        assert mail.outbox[0].to == [agent.email]
        assert customer.email not in mail.outbox[0].to

    def test_an_author_is_not_emailed_about_their_own_note(self, customer, agent):
        ticket = TicketFactory(created_by=customer, assigned_to=agent)
        note = CommentFactory(ticket=ticket, author=agent, is_internal=True)
        mail.outbox.clear()

        notify_comment_added(note.pk)

        assert len(mail.outbox) == 0


class TestScheduleCommand:
    def test_the_command_creates_the_sweep_schedule(self):
        from django.core.management import call_command
        from django_q.models import Schedule

        Schedule.objects.all().delete()
        call_command("setup_schedules")

        schedule = Schedule.objects.get(name="sla-breach-sweep")
        assert schedule.func == "notifications.tasks.check_sla_breaches"
        assert schedule.schedule_type == Schedule.HOURLY
        assert schedule.repeats == -1

    def test_running_it_twice_does_not_duplicate(self):
        from django.core.management import call_command
        from django_q.models import Schedule

        Schedule.objects.all().delete()
        call_command("setup_schedules")
        call_command("setup_schedules")

        assert Schedule.objects.filter(name="sla-breach-sweep").count() == 1
