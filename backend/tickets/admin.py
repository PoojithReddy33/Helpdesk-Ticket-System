from django.contrib import admin

from .models import Comment, StatusChange, Ticket


class CommentInline(admin.TabularInline):
    """Edit comments directly on the ticket page instead of a separate screen."""

    model = Comment
    extra = 0
    fields = ("author", "body", "is_internal", "created_at")
    readonly_fields = ("created_at",)


class StatusChangeInline(admin.TabularInline):
    model = StatusChange
    extra = 0
    fields = ("from_status", "to_status", "changed_by", "created_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        # The audit trail is written by the application, never by hand.
        return False


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "status",
        "priority",
        "created_by",
        "assigned_to",
        "sla_due_at",
        "overdue",
    )
    list_filter = ("status", "priority", "created_at")
    search_fields = ("title", "description", "created_by__email")
    readonly_fields = ("created_at", "updated_at", "sla_due_at")
    autocomplete_fields = ("created_by", "assigned_to")
    date_hierarchy = "created_at"
    inlines = [CommentInline, StatusChangeInline]

    # Fetch both related users in the same query as the tickets, instead of
    # one extra query per row (the N+1 problem).
    list_select_related = ("created_by", "assigned_to")

    @admin.display(boolean=True, description="Overdue")
    def overdue(self, obj):
        return obj.is_overdue


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "author", "is_internal", "created_at")
    list_filter = ("is_internal", "created_at")
    search_fields = ("body",)
    list_select_related = ("ticket", "author")


@admin.register(StatusChange)
class StatusChangeAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status", "created_at")
    list_select_related = ("ticket", "changed_by")
