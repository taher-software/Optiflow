"""Factory for a workstation create/update request payload (`dict`, sent as
the JSON body via `client.post(..., json=WorkstationPayloadFactory())`).
Defaults to an independent workstation (`production_line_id=None`) of
`standard` type so a test only has to override what it cares about."""

import factory

from src.app.globals.enum import WorkstationType


class WorkstationPayloadFactory(factory.Factory):
    class Meta:
        model = dict

    name = factory.Faker("word")
    description = factory.Faker("sentence")
    production_line_id = None
    type = WorkstationType.STANDARD.value
