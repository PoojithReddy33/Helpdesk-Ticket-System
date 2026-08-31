from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    """Custom user model. Logs in with email; carries a helpdesk role."""

    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        AGENT = "AGENT", "Agent"
        ADMIN = "ADMIN", "Admin"

    # AbstractUser ships a required, unique username. We log in with email,
    # so the field is removed entirely rather than left unused.
    username = None

    email = models.EmailField("email address", unique=True)

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        db_index=True,
    )

    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Tells Django which field is the login identifier.
    USERNAME_FIELD = "email"

    # Extra fields createsuperuser should prompt for. USERNAME_FIELD and
    # password are always prompted, so listing them here would be an error.
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"

    @property
    def is_agent(self):
        return self.role == self.Role.AGENT

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER
