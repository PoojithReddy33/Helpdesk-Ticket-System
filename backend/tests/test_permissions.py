"""Who may see and do what. The security boundary, tested per role."""

import pytest

from tickets.models import StatusChange, Ticket

from .factories import CommentFactory, TicketFactory

pytestmark = pytest.mark.django_db


class TestVisibility:
    def test_anonymous_requests_are_rejected(self, api):
        assert api.get("/api/tickets/").status_code == 401

    def test_a_customer_sees_only_their_own_tickets(
        self, as_user, customer, other_customer
    ):
        TicketFactory(created_by=customer)
        TicketFactory(created_by=other_customer)

        response = as_user(customer).get("/api/tickets/")

        assert response.data["count"] == 1
        assert response.data["results"][0]["created_by"]["email"] == customer.email

    def test_an_agent_sees_every_ticket(self, as_user, agent, customer, other_customer):
        TicketFactory(created_by=customer)
        TicketFactory(created_by=other_customer)

        response = as_user(agent).get("/api/tickets/")

        assert response.data["count"] == 2

    def test_someone_elses_ticket_returns_404_not_403(
        self, as_user, customer, other_customer
    ):
        """A 403 would confirm the ticket exists, enabling enumeration."""
        hidden = TicketFactory(created_by=other_customer)

        response = as_user(customer).get(f"/api/tickets/{hidden.pk}/")

        assert response.status_code == 404


class TestTicketActions:
    def test_a_customer_may_open_their_own_ticket(self, as_user, customer):
        ticket = TicketFactory(created_by=customer)

        assert as_user(customer).get(f"/api/tickets/{ticket.pk}/").status_code == 200

    def test_a_customer_may_not_delete_even_their_own_ticket(self, as_user, customer):
        ticket = TicketFactory(created_by=customer)

        assert as_user(customer).delete(f"/api/tickets/{ticket.pk}/").status_code == 403

    def test_an_agent_may_not_delete(self, as_user, agent, customer):
        ticket = TicketFactory(created_by=customer)

        assert as_user(agent).delete(f"/api/tickets/{ticket.pk}/").status_code == 403

    def test_an_admin_may_delete(self, as_user, admin, customer):
        ticket = TicketFactory(created_by=customer)

        response = as_user(admin).delete(f"/api/tickets/{ticket.pk}/")

        assert response.status_code == 204
        assert not Ticket.objects.filter(pk=ticket.pk).exists()


class TestInternalComments:
    def test_internal_notes_are_hidden_from_the_customer(self, as_user, customer, agent):
        ticket = TicketFactory(created_by=customer)
        CommentFactory(ticket=ticket, author=customer, body="Any update?")
        CommentFactory(
            ticket=ticket, author=agent, body="Free plan", is_internal=True
        )

        response = as_user(customer).get(f"/api/tickets/{ticket.pk}/")

        bodies = [c["body"] for c in response.data["comments"]]
        assert bodies == ["Any update?"]

    def test_an_agent_sees_every_comment_on_the_same_ticket(
        self, as_user, customer, agent
    ):
        ticket = TicketFactory(created_by=customer)
        CommentFactory(ticket=ticket, author=customer)
        CommentFactory(ticket=ticket, author=agent, is_internal=True)

        response = as_user(agent).get(f"/api/tickets/{ticket.pk}/")

        assert len(response.data["comments"]) == 2

    def test_a_customer_cannot_write_an_internal_note(self, as_user, customer):
        ticket = TicketFactory(created_by=customer)

        response = as_user(customer).post(
            "/api/comments/",
            {"ticket": ticket.pk, "body": "sneaky", "is_internal": True},
            format="json",
        )

        assert response.status_code == 400
        assert "is_internal" in response.data

    def test_an_agent_can_write_an_internal_note(self, as_user, agent, customer):
        ticket = TicketFactory(created_by=customer)

        response = as_user(agent).post(
            "/api/comments/",
            {"ticket": ticket.pk, "body": "internal", "is_internal": True},
            format="json",
        )

        assert response.status_code == 201

    def test_the_comment_list_hides_internal_notes_from_customers(
        self, as_user, customer, agent
    ):
        ticket = TicketFactory(created_by=customer)
        CommentFactory(ticket=ticket, author=agent, is_internal=True)

        response = as_user(customer).get("/api/comments/")

        assert response.data["count"] == 0


class TestAuditTrail:
    def test_changing_status_records_who_and_when(self, as_user, agent, customer):
        ticket = TicketFactory(created_by=customer, status=Ticket.Status.OPEN)

        as_user(agent).patch(
            f"/api/tickets/{ticket.pk}/",
            {"status": Ticket.Status.IN_PROGRESS},
            format="json",
        )

        change = StatusChange.objects.get(ticket=ticket)
        assert change.from_status == Ticket.Status.OPEN
        assert change.to_status == Ticket.Status.IN_PROGRESS
        assert change.changed_by == agent

    def test_editing_other_fields_writes_no_audit_row(self, as_user, agent, customer):
        ticket = TicketFactory(created_by=customer)

        as_user(agent).patch(
            f"/api/tickets/{ticket.pk}/", {"title": "A new title"}, format="json"
        )

        assert StatusChange.objects.filter(ticket=ticket).count() == 0


class TestCommentOwnership:
    """CommentPermission.has_object_permission - the detail-route rules."""

    def test_a_customer_may_edit_their_own_comment(self, as_user, customer):
        ticket = TicketFactory(created_by=customer)
        comment = CommentFactory(ticket=ticket, author=customer, body="Original")

        response = as_user(customer).patch(
            f"/api/comments/{comment.pk}/", {"body": "Edited"}, format="json"
        )

        assert response.status_code == 200
        assert response.data["body"] == "Edited"

    def test_a_customer_may_not_edit_the_agents_reply(self, as_user, customer, agent):
        ticket = TicketFactory(created_by=customer)
        reply = CommentFactory(ticket=ticket, author=agent, is_internal=False)

        response = as_user(customer).patch(
            f"/api/comments/{reply.pk}/", {"body": "Tampered"}, format="json"
        )

        assert response.status_code == 403

    def test_a_customer_may_read_the_agents_public_reply(self, as_user, customer, agent):
        ticket = TicketFactory(created_by=customer)
        reply = CommentFactory(ticket=ticket, author=agent, is_internal=False)

        assert as_user(customer).get(f"/api/comments/{reply.pk}/").status_code == 200

    def test_a_customer_cannot_reach_a_comment_on_another_persons_ticket(
        self, as_user, customer, other_customer
    ):
        foreign = CommentFactory(
            ticket=TicketFactory(created_by=other_customer), author=other_customer
        )

        response = as_user(customer).get(f"/api/comments/{foreign.pk}/")

        # Filtered out of the queryset entirely, so it simply does not exist.
        assert response.status_code == 404

    def test_an_agent_may_edit_anyones_comment(self, as_user, agent, customer):
        ticket = TicketFactory(created_by=customer)
        comment = CommentFactory(ticket=ticket, author=customer)

        response = as_user(agent).patch(
            f"/api/comments/{comment.pk}/", {"body": "Moderated"}, format="json"
        )

        assert response.status_code == 200

    def test_a_customer_may_delete_their_own_comment(self, as_user, customer):
        ticket = TicketFactory(created_by=customer)
        comment = CommentFactory(ticket=ticket, author=customer)

        assert as_user(customer).delete(f"/api/comments/{comment.pk}/").status_code == 204
