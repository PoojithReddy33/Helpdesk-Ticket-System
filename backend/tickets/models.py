from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Ticket(models.Model):
    """A support request raised by a customer and worked by an agent."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    # How long support has to resolve a ticket, by priority.
    SLA_HOURS = {
        Priority.URGENT: 4,
        Priority.HIGH: 24,
        Priority.MEDIUM: 72,
        Priority.LOW: 168,
    }

    title = models.CharField(max_length=200)
    description = models.TextField()

    # No db_index here: the composite Meta index below starts with `status`,
    # and a composite index already serves queries on its leftmost column.
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.MEDIUM, db_index=True
    )

    # PROTECT: refuse to delete a user who still has tickets, so history is
    # never silently destroyed.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_tickets",
    )

    # SET_NULL: if an agent leaves, the ticket survives and falls back to
    # unassigned.
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
        limit_choices_to={"role": "AGENT"},
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    sla_due_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # Supports the common "my open urgent tickets" style filter.
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["assigned_to", "status"]),
        ]

    def __str__(self):
        return f"#{self.pk} {self.title}"

    def save(self, *args, **kwargs):
        # Set the SLA deadline once, when the ticket is first created.
        if self.sla_due_at is None:
            hours = self.SLA_HOURS.get(self.priority, 72)
            self.sla_due_at = timezone.now() + timedelta(hours=hours)
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        if self.sla_due_at is None or self.status in {
            self.Status.RESOLVED,
            self.Status.CLOSED,
        }:
            return False
        return timezone.now() > self.sla_due_at

    @property
    def is_open(self):
        return self.status in {self.Status.OPEN, self.Status.IN_PROGRESS}


class Comment(models.Model):
    """A message on a ticket, from either the customer or an agent."""

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="comments",
    )
    body = models.TextField()

    # Internal notes are visible to agents and admins only, never to the
    # customer who raised the ticket.
    is_internal = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author} on ticket #{self.ticket_id}"


class StatusChange(models.Model):
    """Audit trail: one row per status transition on a ticket."""

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="status_changes"
    )
    changed_by = models.ForeignKey( 
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="status_changes",
    )

    # Blank on the first entry, where the ticket was created rather than moved.
    from_status = models.CharField(
        max_length=20, choices=Ticket.Status.choices, blank=True
    )
    to_status = models.CharField(max_length=20, choices=Ticket.Status.choices)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        origin = self.from_status or "new"
        return f"Ticket #{self.ticket_id}: {origin} -> {self.to_status}"
