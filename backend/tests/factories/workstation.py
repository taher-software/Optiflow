"""Factory for a workstation create/update request payload (`dict`, sent as
the JSON body via `client.post(..., json=WorkstationPayloadFactory())`).
Defaults to an independent workstation (`production_line_id=None`) of
`standard` type so a test only has to override what it cares about.

`WorkstationDocFactory` builds a raw Firestore document (as written by
`src.app.routers.workstation.services.create_workstation`), ready to be
seeded straight into the fake Firestore client — used by tests for other
resources (e.g. down_time) that need a pre-existing workstation without
going through the `/workstations` endpoint.
"""

import uuid

import factory

from src.app.globals.enum import WorkstationType


class WorkstationPayloadFactory(factory.Factory):
    class Meta:
        model = dict

    name = factory.Faker("word")
    description = factory.Faker("sentence")
    production_line_id = None
    type = WorkstationType.STANDARD.value


class WorkstationDocFactory(factory.Factory):
    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    namespace_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    name = factory.Faker("word")
    description = factory.Faker("sentence")
    production_line_id = None
    type = WorkstationType.STANDARD.value
