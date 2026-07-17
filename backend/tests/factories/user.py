"""Factory for a `Users` collection document.

Firestore is schemaless, so there is no ORM model to back a `DjangoModelFactory`
-equivalent: this factory builds a plain `dict` matching the shape written by
`src.app.routers.registration.services.create_account` /
`src.app.routers.user.services`, ready to be seeded straight into the fake
Firestore client with `.collection(USERS_COLLECTION).document(id).set(user)`.
"""

import uuid

import factory

from src.app.globals.enum import Role


class UserFactory(factory.Factory):
    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    namespace_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.Faker("email")
    avatar_url = None
    role = Role.MAINTENANCE_AGENT.value
    password = "hashed-password"
