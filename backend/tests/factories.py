"""Factories build valid model objects so each test states only what it cares about."""

import factory

from accounts.models import User
from tickets.models import Comment, Ticket


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    # Sequence guarantees a unique email per object, so the unique
    # constraint never collides between tests.
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = factory.Faker("first_name")
    role = User.Role.CUSTOMER

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        # Hash a real password so login tests can authenticate.
        obj.set_password(extracted or "Test@12345")
        if create:
            obj.save()


class AgentFactory(UserFactory):
    role = User.Role.AGENT


class AdminFactory(UserFactory):
    role = User.Role.ADMIN
    is_staff = True
    is_superuser = True


class TicketFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ticket

    title = factory.Sequence(lambda n: f"Ticket number {n}")
    description = factory.Faker("sentence")
    priority = Ticket.Priority.MEDIUM
    # SubFactory builds a related object automatically when none is given.
    created_by = factory.SubFactory(UserFactory)


class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Comment

    ticket = factory.SubFactory(TicketFactory)
    author = factory.SubFactory(UserFactory)
    body = factory.Faker("sentence")
    is_internal = False
