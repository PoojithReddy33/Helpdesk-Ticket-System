from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models import User


class IsAdmin(BasePermission):
    """Admins only."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.Role.ADMIN


class IsAgentOrAdmin(BasePermission):
    """Staff-side roles."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in {
            User.Role.AGENT,
            User.Role.ADMIN,
        }


class TicketPermission(BasePermission):
    """Who may act on a ticket.

    Customers   - create tickets, read and edit only their own.
    Agents      - read and edit every ticket, but not delete.
    Admins      - everything.
    """

    def has_permission(self, request, view):
        # Runs before the object is loaded, so it can only judge the action.
        if not request.user.is_authenticated:
            return False
        if view.action == "destroy":
            return request.user.role == User.Role.ADMIN
        return True

    def has_object_permission(self, request, view, obj):
        # Runs only for detail routes, once the ticket has been fetched.
        user = request.user

        if user.role in {User.Role.AGENT, User.Role.ADMIN}:
            return True

        # Customers are confined to tickets they raised.
        return obj.created_by_id == user.id


class CommentPermission(BasePermission):
    """Customers may comment on their own tickets; staff on any ticket."""

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.role in {User.Role.AGENT, User.Role.ADMIN}:
            return True

        # A customer must own the parent ticket, and may only read internal
        # notes never - those are filtered out of the queryset entirely.
        if obj.ticket.created_by_id != user.id:
            return False

        # Customers may read any of their own visible comments, but only
        # edit or delete the ones they wrote.
        if request.method in SAFE_METHODS:
            return True
        return obj.author_id == user.id
