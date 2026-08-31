from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Manager for the custom User model, keyed on email instead of username."""

    # Lets migrations serialize this manager, so data migrations can create users.
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """Shared logic for both create_user and create_superuser."""
        if not email:
            raise ValueError("Users must have an email address")

        # Lowercases the domain part so Foo@Example.com and foo@example.com
        # cannot both be registered as separate accounts.
        email = self.normalize_email(email)

        user = self.model(email=email, **extra_fields)

        # Hashes the password. Never assign user.password directly — that would
        # store the raw text.
        user.set_password(password)

        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", self.model.Role.CUSTOMER)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", self.model.Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)
