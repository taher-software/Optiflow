"""Factory for a `namespace` (tenant/plant) collection document.

`NamespaceDocFactory` builds a raw Firestore document, ready to be seeded
straight into the fake Firestore client — used by tests that need a
pre-existing namespace (e.g. to exercise the `add_down_time` handler's
timezone resolution) without going through `/registration`."""

import uuid

import factory


class NamespaceDocFactory(factory.Factory):
    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    company_name = factory.Faker("company")
    adress = factory.Faker("address")
    code_postal = factory.Faker("postcode")
    phone_number = factory.Faker("phone_number")
    tax_identification_number = factory.Faker("bothify", text="??########")
    country = factory.Faker("country")
    city = factory.Faker("city")
    confirmed = True
    timezone = None
    language = "en"
