"""Fixtures available to every test without importing them."""

import pytest
from rest_framework.test import APIClient

from tests.factories import (
    AdminFactory,
    AgentFactory,
    CommentFactory,
    TicketFactory,
    UserFactory,
)


@pytest.fixture
def api():
    """An unauthenticated API client."""
    return APIClient()


@pytest.fixture
def customer(db):
    return UserFactory()


@pytest.fixture
def other_customer(db):
    return UserFactory()


@pytest.fixture
def agent(db):
    return AgentFactory()


@pytest.fixture
def admin(db):
    return AdminFactory()


@pytest.fixture
def as_user(api):
    """Authenticate the shared client as a given user, bypassing JWT."""

    def _as_user(user):
        api.force_authenticate(user=user)
        return api

    return _as_user


@pytest.fixture
def jwt_login(api):
    """Log in over the real endpoint and return the token payload."""

    def _login(email, password="Test@12345"):
        response = api.post(
            "/api/auth/login/",
            {"email": email, "password": password},
            format="json",
        )
        return response

    return _login


@pytest.fixture
def ticket_factory():
    return TicketFactory


@pytest.fixture
def comment_factory():
    return CommentFactory
