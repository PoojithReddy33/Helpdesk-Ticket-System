from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from django_q.tasks import async_task
from rest_framework import filters, viewsets

from accounts.models import User

from .models import Comment, Ticket
from .permissions import CommentPermission, TicketPermission
from .serializers import CommentSerializer, TicketDetailSerializer, TicketSerializer


class TicketViewSet(viewsets.ModelViewSet):
    """Full CRUD for tickets, scoped to what the caller is allowed to see."""

    queryset = Ticket.objects.select_related("created_by", "assigned_to")
    permission_classes = [TicketPermission]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["status", "priority", "assigned_to"]
    search_fields = ["title", "description", "created_by__email"]
    ordering_fields = ["created_at", "sla_due_at", "priority"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return TicketDetailSerializer
        return TicketSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # The security boundary. Customers never receive rows they don't own,
        # so there is nothing for them to guess the id of.
        if user.role == User.Role.CUSTOMER:
            qs = qs.filter(created_by=user)

        if self.action == "retrieve":
            qs = qs.prefetch_related("comments__author", "status_changes__changed_by")
        return qs

    def perform_create(self, serializer):
        ticket = serializer.save(created_by=self.request.user)

        # on_commit defers the enqueue until the row is actually committed.
        # Without it a worker could pick the job up and query for a ticket
        # that is not visible to its connection yet.
        transaction.on_commit(
            lambda: async_task(
                "notifications.tasks.notify_ticket_created", ticket.pk
            )
        )

    def perform_update(self, serializer):
        # Capture the stored status before the new one overwrites it.
        previous_status = Ticket.objects.get(pk=serializer.instance.pk).status
        ticket = serializer.save()

        if ticket.status != previous_status:
            ticket.status_changes.create(
                from_status=previous_status,
                to_status=ticket.status,
                changed_by=self.request.user,
            )

            new_status = ticket.status
            actor_id = self.request.user.pk
            transaction.on_commit(
                lambda: async_task(
                    "notifications.tasks.notify_status_changed",
                    ticket.pk,
                    previous_status,
                    new_status,
                    actor_id,
                )
            )


class CommentViewSet(viewsets.ModelViewSet):
    queryset = Comment.objects.select_related("author", "ticket")
    serializer_class = CommentSerializer
    permission_classes = [CommentPermission]

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["ticket", "is_internal"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == User.Role.CUSTOMER:
            # Own tickets only, and internal notes are stripped out.
            qs = qs.filter(ticket__created_by=user, is_internal=False)
        return qs

    def perform_create(self, serializer):
        comment = serializer.save(author=self.request.user)

        transaction.on_commit(
            lambda: async_task(
                "notifications.tasks.notify_comment_added", comment.pk
            )
        )
