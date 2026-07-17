"""Factory for a UAP create/update request payload (`dict`, sent as the JSON
body via `client.post(..., json=UapPayloadFactory())`). Defaults to no member
ids in any of the 8 lists so a test only has to override the lists it cares
about."""

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
