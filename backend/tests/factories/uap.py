"""Factories for the UAP (production area) resource.

`UapPayloadFactory` builds a create/update request payload (`dict`, sent as
the JSON body via `client.post(..., json=UapPayloadFactory())`). Defaults to
no member ids in any of the 8 lists so a test only has to override the lists
it cares about.

`UapDocFactory` builds a raw Firestore document (as written by
`src.app.routers.uap.services.create_uap`), ready to be seeded straight into
the fake Firestore client — used by tests for other resources (e.g.
production_line) that need a pre-existing UAP without going through the
`/uaps` endpoint.
"""

import uuid

import factory


class UapPayloadFactory(factory.Factory):
    class Meta:
        model = dict

    name = factory.Faker("company")
    description = factory.Faker("sentence")
    maintenance_agent_ids = factory.LazyFunction(list)
    production_agent_ids = factory.LazyFunction(list)
    quality_agent_ids = factory.LazyFunction(list)
    logistic_agent_ids = factory.LazyFunction(list)
    logistic_supervisor_ids = factory.LazyFunction(list)
    maintenance_supervisor_ids = factory.LazyFunction(list)
    quality_supervisor_ids = factory.LazyFunction(list)
    production_supervisor_ids = factory.LazyFunction(list)


class UapDocFactory(factory.Factory):
    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    namespace_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    name = factory.Faker("company")
    description = factory.Faker("sentence")
    maintenance_agent_ids = factory.LazyFunction(list)
    production_agent_ids = factory.LazyFunction(list)
    quality_agent_ids = factory.LazyFunction(list)
    logistic_agent_ids = factory.LazyFunction(list)
    logistic_supervisor_ids = factory.LazyFunction(list)
    maintenance_supervisor_ids = factory.LazyFunction(list)
    quality_supervisor_ids = factory.LazyFunction(list)
    production_supervisor_ids = factory.LazyFunction(list)
