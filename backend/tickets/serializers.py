from rest_framework import serializers

from accounts.models import User

from .models import Comment, StatusChange, Ticket


class UserBriefSerializer(serializers.ModelSerializer):
    """A compact user, for nesting inside ticket and comment responses."""

    class Meta:
        model = User
        fields = ["id", "email", "role"]


class CommentSerializer(serializers.ModelSerializer):
    # Nested object on output; the author is taken from the logged-in user
    # on input, never accepted from the client.
    author = UserBriefSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "ticket", "author", "body", "is_internal", "created_at"]
        read_only_fields = ["id", "author", "created_at"]

    def validate_is_internal(self, value):
        request = self.context.get("request")
        if value and request and request.user.role == User.Role.CUSTOMER:
            raise serializers.ValidationError(
                "Only agents and admins can write internal notes."
            )
        return value


class StatusChangeSerializer(serializers.ModelSerializer):
    changed_by = UserBriefSerializer(read_only=True)

    class Meta:
        model = StatusChange
        fields = ["id", "from_status", "to_status", "changed_by", "created_at"]


class TicketSerializer(serializers.ModelSerializer):
    """Used for the list endpoint and for create/update."""

    # Read side: full nested objects so the client gets emails, not just ids.
    created_by = UserBriefSerializer(read_only=True)
    assigned_to = UserBriefSerializer(read_only=True)

    # Write side: the client sends an id, which DRF resolves to a User.
    assigned_to_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.AGENT),
        source="assigned_to",
        write_only=True,
        required=False,
        allow_null=True,
    )

    # The human label, e.g. "In Progress" instead of "IN_PROGRESS".
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(
        source="get_priority_display", read_only=True
    )

    # A model @property exposed as a JSON field.
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "title",
            "description",
            "status",
            "status_display",
            "priority",
            "priority_display",
            "created_by",
            "assigned_to",
            "assigned_to_id",
            "created_at",
            "updated_at",
            "sla_due_at",
            "is_overdue",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at", "sla_due_at"]

    # Fields only staff may set. A customer raising a ticket cannot decide
    # its status or pick which agent handles it.
    STAFF_ONLY_FIELDS = {"status", "assigned_to", "priority"}

    def validate_title(self, value):
        """Field-level validation: DRF calls this automatically for `title`."""
        if len(value.strip()) < 5:
            raise serializers.ValidationError(
                "Title must be at least 5 characters long."
            )
        return value.strip()

    def validate(self, attrs):
        """Object-level validation: sees every field at once."""
        request = self.context.get("request")
        if request is None:
            return attrs

        if request.user.role == User.Role.CUSTOMER:
            attempted = self.STAFF_ONLY_FIELDS & set(attrs)
            if attempted:
                raise serializers.ValidationError(
                    {
                        field: "Only agents and admins can set this field."
                        for field in sorted(attempted)
                    }
                )
        return attrs


class TicketDetailSerializer(TicketSerializer):
    """Everything the list serializer has, plus the ticket's history."""

    # A method field, not a plain nested serializer, because which comments
    # are visible depends on who is asking.
    comments = serializers.SerializerMethodField()
    status_changes = StatusChangeSerializer(many=True, read_only=True)

    def get_comments(self, obj):
        qs = obj.comments.all()
        request = self.context.get("request")

        if request and request.user.role == User.Role.CUSTOMER:
            qs = [c for c in qs if not c.is_internal]

        return CommentSerializer(qs, many=True, context=self.context).data

    class Meta(TicketSerializer.Meta):
        fields = TicketSerializer.Meta.fields + ["comments", "status_changes"]
