"""Model-level behaviour: the business rules that live in models.py."""

from datetime import timedelta

import pytest
from django.db.models import ProtectedError
from django.utils import timezone

from tickets.models import Comment, StatusChange, Ticket

from .factories import CommentFactory, TicketFactory, UserFactory

# Every test in this module needs database access.
pytestmark = pytest.mark.django_db


class TestSlaCalculation:
    @pytest.mark.parametrize(
        "priority,expected_hours",
        [
            (Ticket.Priority.URGENT, 4),
            (Ticket.Priority.HIGH, 24),
            (Ticket.Priority.MEDIUM, 72),
            (Ticket.Priority.LOW, 168),
        ],
    )
    def test_deadline_matches_priority(self, priority, expected_hours):
        ticket = TicketFactory(priority=priority)

        gap = ticket.sla_due_at - ticket.created_at
        # Allow a second of slack: created_at and sla_due_at are stamped
        # microseconds apart.
        assert abs(gap - timedelta(hours=expected_hours)) < timedelta(seconds=2)

    def test_deadline_is_set_once_and_never_extended(self):
        ticket = TicketFactory(priority=Ticket.Priority.LOW)
        original = ticket.sla_due_at

        ticket.priority = Ticket.Priority.URGENT
        ticket.save()
        ticket.refresh_from_db()

        assert ticket.sla_due_at == original


class TestOverdue:
    def test_past_deadline_is_overdue(self):
        ticket = TicketFactory()
        ticket.sla_due_at = timezone.now() - timedelta(hours=1)

        assert ticket.is_overdue is True

    def test_future_deadline_is_not_overdue(self):
        assert TicketFactory().is_overdue is False

    @pytest.mark.parametrize(
        "status", [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]
    )
    def test_finished_tickets_are_never_overdue(self, status):
        ticket = TicketFactory(status=status)
        ticket.sla_due_at = timezone.now() - timedelta(days=5)

        assert ticket.is_overdue is False


class TestDeletionRules:
    def test_user_with_tickets_cannot_be_deleted(self):
        """on_delete=PROTECT keeps support history intact."""
        ticket = TicketFactory()

        with pytest.raises(ProtectedError):
            ticket.created_by.delete()

    def test_deleting_an_agent_unassigns_their_tickets(self):
        """on_delete=SET_NULL: the ticket survives, the assignment doesn't."""
        agent = UserFactory(role="AGENT")
        ticket = TicketFactory(assigned_to=agent)

        agent.delete()
        ticket.refresh_from_db()

        assert ticket.assigned_to is None

    def test_deleting_a_ticket_removes_its_comments(self):
        """on_delete=CASCADE: a comment has no meaning without its ticket."""
        comment = CommentFactory()
        ticket_id = comment.ticket_id

        Ticket.objects.filter(pk=ticket_id).delete()

        assert not Comment.objects.filter(ticket_id=ticket_id).exists()


class TestStringRepresentations:
    def test_user_str_shows_email_and_role_label(self):
        user = UserFactory(email="poojith@example.com")
        assert str(user) == "poojith@example.com (Customer)"

    def test_ticket_str_shows_id_and_title(self):
        ticket = TicketFactory(title="Printer on fire")
        assert str(ticket) == f"#{ticket.pk} Printer on fire"

    def test_status_change_shows_new_for_a_blank_origin(self):
        ticket = TicketFactory()
        change = StatusChange.objects.create(
            ticket=ticket, from_status="", to_status=Ticket.Status.OPEN
        )
        assert "new -> OPEN" in str(change)
