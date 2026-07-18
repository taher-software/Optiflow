"""Factories for the `production_line` resource.

`ProductionLinePayloadFactory` builds a create/update request payload (`dict`,
sent as the JSON body via `client.post(..., json=ProductionLinePayloadFactory())`).

`ProductionLineDocFactory` builds a raw Firestore document (as written by
`src.app.routers.production_line.services.create_production_line`), ready to
be seeded straight into the fake Firestore client — used by tests for other
resources (e.g. workstation) that need a pre-existing production line without
going through the `/production-lines` endpoint.
"""

import uuid

import factory


class ProductionLinePayloadFactory(factory.Factory):
    class Meta:
        model = dict

    name = factory.Faker("company")
    description = factory.Faker("sentence")
    uap_id = ""


class ProductionLineDocFactory(factory.Factory):
    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    namespace_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    name = factory.Faker("company")
    description = factory.Faker("sentence")
    uap_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
