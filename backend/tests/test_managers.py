"""The custom user manager - the only place passwords get hashed."""

import pytest

from accounts.models import User

pytestmark = pytest.mark.django_db


class TestCreateUser:
    def test_email_is_required(self):
        with pytest.raises(ValueError, match="Users must have an email address"):
            User.objects.create_user(email="", password="Str0ng!Pass9")

    def test_the_domain_is_normalised_to_lowercase(self):
        user = User.objects.create_user(
            email="Poojith@EXAMPLE.COM", password="Str0ng!Pass9"
        )

        # The local part is case-sensitive by spec, so only the domain changes.
        assert user.email == "Poojith@example.com"

    def test_new_users_default_to_customer(self):
        user = User.objects.create_user(
            email="default@example.com", password="Str0ng!Pass9"
        )

        assert user.role == User.Role.CUSTOMER
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_an_explicit_role_still_wins(self):
        user = User.objects.create_user(
            email="agent@example.com", password="Str0ng!Pass9", role=User.Role.AGENT
        )

        assert user.role == User.Role.AGENT

    def test_the_password_is_hashed_never_stored_raw(self):
        user = User.objects.create_user(
            email="hash@example.com", password="Str0ng!Pass9"
        )

        assert user.password != "Str0ng!Pass9"
        assert user.check_password("Str0ng!Pass9")


class TestCreateSuperuser:
    def test_a_superuser_gets_staff_and_admin_role(self):
        user = User.objects.create_superuser(
            email="boss@example.com", password="Str0ng!Pass9"
        )

        assert user.is_staff is True
        assert user.is_superuser is True
        assert user.role == User.Role.ADMIN

    def test_a_superuser_without_staff_is_a_contradiction(self):
        with pytest.raises(ValueError, match="Superuser must have is_staff=True"):
            User.objects.create_superuser(
                email="broken@example.com", password="Str0ng!Pass9", is_staff=False
            )

    def test_a_superuser_without_the_superuser_flag_is_rejected(self):
        with pytest.raises(ValueError, match="Superuser must have is_superuser=True"):
            User.objects.create_superuser(
                email="broken2@example.com",
                password="Str0ng!Pass9",
                is_superuser=False,
            )


class TestRoleProperties:
    def test_is_agent_and_is_customer_reflect_the_role(self):
        agent = User.objects.create_user(
            email="a@example.com", password="Str0ng!Pass9", role=User.Role.AGENT
        )
        customer = User.objects.create_user(
            email="c@example.com", password="Str0ng!Pass9"
        )

        assert agent.is_agent is True
        assert agent.is_customer is False
        assert customer.is_customer is True
        assert customer.is_agent is False
