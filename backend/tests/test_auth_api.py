"""Registration, login, tokens, and the profile endpoint."""

import base64
import json

import pytest

from accounts.models import User

pytestmark = pytest.mark.django_db


def decode_payload(token):
    """A JWT payload is base64 JSON - no secret needed to read it."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)  # restore stripped padding
    return json.loads(base64.urlsafe_b64decode(payload))


class TestRegistration:
    def test_anyone_can_register(self, api):
        response = api.post(
            "/api/auth/register/",
            {
                "email": "newuser@example.com",
                "password": "Str0ng!Pass9",
                "password_confirm": "Str0ng!Pass9",
                "first_name": "New",
            },
            format="json",
        )

        assert response.status_code == 201
        assert User.objects.filter(email="newuser@example.com").exists()

    def test_registration_never_returns_the_password(self, api):
        response = api.post(
            "/api/auth/register/",
            {
                "email": "quiet@example.com",
                "password": "Str0ng!Pass9",
                "password_confirm": "Str0ng!Pass9",
            },
            format="json",
        )

        assert "password" not in response.data
        assert "password_confirm" not in response.data

    def test_signup_always_creates_a_customer(self, api):
        """Even when the payload asks for ADMIN."""
        api.post(
            "/api/auth/register/",
            {
                "email": "sneaky@example.com",
                "password": "Str0ng!Pass9",
                "password_confirm": "Str0ng!Pass9",
                "role": "ADMIN",
            },
            format="json",
        )

        assert User.objects.get(email="sneaky@example.com").role == User.Role.CUSTOMER

    def test_mismatched_passwords_are_rejected(self, api):
        response = api.post(
            "/api/auth/register/",
            {
                "email": "mismatch@example.com",
                "password": "Str0ng!Pass9",
                "password_confirm": "something-else",
            },
            format="json",
        )

        assert response.status_code == 400
        assert "password_confirm" in response.data

    def test_weak_passwords_are_rejected(self, api):
        """Reuses Django's AUTH_PASSWORD_VALIDATORS."""
        response = api.post(
            "/api/auth/register/",
            {
                "email": "weak@example.com",
                "password": "abc",
                "password_confirm": "abc",
            },
            format="json",
        )

        assert response.status_code == 400
        assert "password" in response.data

    def test_password_is_stored_hashed(self, api):
        api.post(
            "/api/auth/register/",
            {
                "email": "hashed@example.com",
                "password": "Str0ng!Pass9",
                "password_confirm": "Str0ng!Pass9",
            },
            format="json",
        )

        user = User.objects.get(email="hashed@example.com")
        assert user.password != "Str0ng!Pass9"
        assert user.password.startswith("pbkdf2_sha256$")
        assert user.check_password("Str0ng!Pass9")


class TestLogin:
    def test_login_returns_both_tokens_and_the_profile(self, jwt_login, customer):
        response = jwt_login(customer.email)

        assert response.status_code == 200
        assert set(response.data) == {"refresh", "access", "user"}
        assert response.data["user"]["email"] == customer.email

    def test_token_carries_email_and_role_claims(self, jwt_login, agent):
        response = jwt_login(agent.email)

        payload = decode_payload(response.data["access"])
        assert payload["email"] == agent.email
        assert payload["role"] == "AGENT"

    def test_wrong_password_is_rejected(self, jwt_login, customer):
        assert jwt_login(customer.email, "wrong-password").status_code == 401

    def test_unknown_email_is_rejected(self, jwt_login):
        assert jwt_login("nobody@example.com").status_code == 401


class TestTokenUsage:
    def test_a_real_token_grants_access(self, api, jwt_login, customer):
        token = jwt_login(customer.email).data["access"]

        response = api.get(
            "/api/tickets/", HTTP_AUTHORIZATION=f"Bearer {token}"
        )

        assert response.status_code == 200

    def test_a_tampered_token_is_rejected(self, api, jwt_login, customer):
        token = jwt_login(customer.email).data["access"]
        tampered = token[:-3] + "abc"

        response = api.get(
            "/api/tickets/", HTTP_AUTHORIZATION=f"Bearer {tampered}"
        )

        assert response.status_code == 401

    def test_refresh_returns_a_new_access_token(self, api, jwt_login, customer):
        refresh = jwt_login(customer.email).data["refresh"]

        response = api.post(
            "/api/auth/token/refresh/", {"refresh": refresh}, format="json"
        )

        assert response.status_code == 200
        assert "access" in response.data
        # ROTATE_REFRESH_TOKENS is on, so a new refresh comes back too.
        assert "refresh" in response.data


class TestProfile:
    def test_profile_requires_authentication(self, api):
        assert api.get("/api/auth/me/").status_code == 401

    def test_profile_returns_the_caller_without_any_id_in_the_url(
        self, as_user, customer
    ):
        response = as_user(customer).get("/api/auth/me/")

        assert response.status_code == 200
        assert response.data["email"] == customer.email

    def test_a_user_cannot_promote_themselves(self, as_user, customer):
        """role is read-only, so mass assignment cannot escalate privileges."""
        response = as_user(customer).patch(
            "/api/auth/me/", {"first_name": "Riya", "role": "ADMIN"}, format="json"
        )

        customer.refresh_from_db()
        assert response.status_code == 200
        assert customer.first_name == "Riya"
        assert customer.role == User.Role.CUSTOMER
