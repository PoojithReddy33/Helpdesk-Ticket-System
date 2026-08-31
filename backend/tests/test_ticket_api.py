"""The ticket endpoints: creation, validation, filtering, and query efficiency."""

import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection

from tickets.models import Ticket

from .factories import TicketFactory

pytestmark = pytest.mark.django_db


class TestCreation:
    def test_the_creator_comes_from_the_token_not_the_payload(self, as_user, customer, other_customer):
        response = as_user(customer).post(
            "/api/tickets/",
            {
                "title": "Laptop will not boot",
                "description": "Black screen after the update.",
                "created_by": other_customer.pk,  # forged, must be ignored
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["created_by"]["email"] == customer.email

    def test_the_sla_deadline_is_applied_through_the_api(self, as_user, agent):
        """Model logic runs for API writes too - it isn't duplicated in the view."""
        response = as_user(agent).post(
            "/api/tickets/",
            {"title": "Server room too hot", "description": "35C", "priority": "URGENT"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["sla_due_at"] is not None

    def test_a_customer_still_gets_a_deadline_on_the_default_priority(
        self, as_user, customer
    ):
        response = as_user(customer).post(
            "/api/tickets/",
            {"title": "Mouse not working", "description": "No cursor movement."},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["priority"] == Ticket.Priority.MEDIUM
        assert response.data["sla_due_at"] is not None

    def test_a_new_ticket_starts_open(self, as_user, customer):
        response = as_user(customer).post(
            "/api/tickets/",
            {"title": "Wifi keeps dropping", "description": "Every ten minutes."},
            format="json",
        )

        assert response.data["status"] == Ticket.Status.OPEN


class TestValidation:
    def test_a_short_title_is_rejected(self, as_user, customer):
        response = as_user(customer).post(
            "/api/tickets/", {"title": "abc", "description": "x"}, format="json"
        )

        assert response.status_code == 400
        assert "title" in response.data

    def test_a_whitespace_only_title_is_rejected(self, as_user, customer):
        response = as_user(customer).post(
            "/api/tickets/", {"title": "        ", "description": "x"}, format="json"
        )

        assert response.status_code == 400

    def test_titles_are_trimmed_before_saving(self, as_user, customer):
        response = as_user(customer).post(
            "/api/tickets/",
            {"title": "   Printer jam   ", "description": "Tray 2"},
            format="json",
        )

        assert response.data["title"] == "Printer jam"

    @pytest.mark.parametrize("field,value", [
        ("priority", "URGENT"),
        ("status", "CLOSED"),
    ])
    def test_a_customer_cannot_set_staff_only_fields(
        self, as_user, customer, field, value
    ):
        """Customers may not declare their own urgency or close their own ticket."""
        response = as_user(customer).post(
            "/api/tickets/",
            {"title": "Escalate me please", "description": "x", field: value},
            format="json",
        )

        assert response.status_code == 400
        assert field in response.data

    def test_an_agent_may_set_staff_only_fields(self, as_user, agent):
        response = as_user(agent).post(
            "/api/tickets/",
            {"title": "Escalated by staff", "description": "x", "priority": "URGENT"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["priority"] == "URGENT"

    def test_a_ticket_cannot_be_assigned_to_a_customer(self, as_user, agent, customer):
        """The queryset on assigned_to_id only contains agents."""
        response = as_user(agent).post(
            "/api/tickets/",
            {
                "title": "Assign to the wrong person",
                "description": "x",
                "assigned_to_id": customer.pk,
            },
            format="json",
        )

        assert response.status_code == 400
        assert "assigned_to_id" in response.data


class TestSerializerShape:
    def test_the_list_omits_comments(self, as_user, customer):
        TicketFactory(created_by=customer)

        response = as_user(customer).get("/api/tickets/")

        assert "comments" not in response.data["results"][0]

    def test_the_detail_view_includes_comments_and_history(self, as_user, customer):
        ticket = TicketFactory(created_by=customer)

        response = as_user(customer).get(f"/api/tickets/{ticket.pk}/")

        assert "comments" in response.data
        assert "status_changes" in response.data

    def test_human_labels_travel_alongside_stored_values(self, as_user, customer):
        TicketFactory(created_by=customer, status=Ticket.Status.IN_PROGRESS)

        row = as_user(customer).get("/api/tickets/").data["results"][0]

        assert row["status"] == "IN_PROGRESS"
        assert row["status_display"] == "In Progress"

    def test_related_users_are_nested_not_bare_ids(self, as_user, customer):
        TicketFactory(created_by=customer)

        row = as_user(customer).get("/api/tickets/").data["results"][0]

        assert row["created_by"]["email"] == customer.email


class TestFiltering:
    def test_filter_by_status(self, as_user, agent, customer):
        TicketFactory(created_by=customer, status=Ticket.Status.OPEN)
        TicketFactory(created_by=customer, status=Ticket.Status.CLOSED)

        response = as_user(agent).get("/api/tickets/?status=OPEN")

        assert response.data["count"] == 1

    def test_search_reaches_through_the_foreign_key(self, as_user, agent, customer):
        """created_by__email is searchable, so a name finds a ticket."""
        TicketFactory(created_by=customer, title="Nothing relevant here")

        local_part = customer.email.split("@")[0]
        response = as_user(agent).get(f"/api/tickets/?search={local_part}")

        assert response.data["count"] == 1

    def test_ordering_can_be_reversed(self, as_user, agent, customer):
        first = TicketFactory(created_by=customer)
        second = TicketFactory(created_by=customer)

        newest_first = as_user(agent).get("/api/tickets/").data["results"]
        oldest_first = as_user(agent).get("/api/tickets/?ordering=created_at").data["results"]

        assert newest_first[0]["id"] == second.pk
        assert oldest_first[0]["id"] == first.pk


class TestQueryEfficiency:
    def test_the_list_endpoint_does_not_scale_its_query_count(
        self, as_user, agent, customer
    ):
        """select_related keeps the count flat as rows are added - no N+1."""
        TicketFactory.create_batch(3, created_by=customer)
        client = as_user(agent)

        with CaptureQueriesContext(connection) as few:
            client.get("/api/tickets/")

        TicketFactory.create_batch(12, created_by=customer)

        with CaptureQueriesContext(connection) as many:
            client.get("/api/tickets/")

        assert len(many.captured_queries) == len(few.captured_queries)
