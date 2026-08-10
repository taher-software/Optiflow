"""API tests for `POST /registration`: namespace-language derivation.

`create_account` derives the namespace `language` field server-side from
`company.country` (see `src.app.globals.enum.resolve_default_language`) — the
request body has no `language` field to send in the first place, so these
tests also assert that an attempt to smuggle one in has no effect.

No real network is touched: `send_confirmation_email` is monkeypatched so the
Resend SDK is never invoked.
"""

import pytest

import src.app.core.email as email_module
from src.app.core.firestore import NAMESPACE_COLLECTION

REGISTER_URL = "/registration"


@pytest.fixture(autouse=True)
def _email_spy(monkeypatch):
    """Never hit Resend/network for the confirmation email."""
    calls: list[dict] = []

    def _spy(to, confirm_url):
        calls.append({"to": to, "confirm_url": confirm_url})

    monkeypatch.setattr(email_module, "send_confirmation_email", _spy)
    return calls


def _payload(**company_overrides):
    company = {
        "company_name": "Acme Manufacturing",
        "adress": "1 Rue de la Paix",
        "code_postal": "75002",
        "phone_number": "+33123456789",
        "tax_identification_number": "FR12345678901",
        "country": "France",
        "city": "Paris",
    }
    company.update(company_overrides)
    return {
        "company": company,
        "owner": {
            "firstname": "Jane",
            "lastname": "Doe",
            "email": "jane.doe@example.com",
        },
    }


def _namespace(fake_db, namespace_id):
    doc = (
        fake_db.collection(NAMESPACE_COLLECTION).document(namespace_id).get().to_dict()
    )
    return doc


class TestRegistrationLanguage:
    def test_french_list_country_persists_fr_language(self, client, fake_db):
        res = client.post(REGISTER_URL, json=_payload(country="Tunisia"))
        assert res.status_code == 201, res.text
        namespace_id = res.json()["data"]["namespace_id"]
        assert _namespace(fake_db, namespace_id)["language"] == "fr"

    def test_non_french_list_country_persists_en_language(self, client, fake_db):
        res = client.post(REGISTER_URL, json=_payload(country="Germany"))
        assert res.status_code == 201, res.text
        namespace_id = res.json()["data"]["namespace_id"]
        assert _namespace(fake_db, namespace_id)["language"] == "en"

    def test_language_is_not_accepted_from_request_body(self, client, fake_db):
        """`language` is derived server-side — it is not a field on
        `RegisterAccountIn`, so attempting to send one in the payload has no
        effect on the persisted value (still derived from `country`)."""
        payload = _payload(country="Germany")
        payload["company"]["language"] = "fr"  # not a real field, should be ignored

        res = client.post(REGISTER_URL, json=payload)
        assert res.status_code == 201, res.text
        namespace_id = res.json()["data"]["namespace_id"]
        # Country is non-French-list, so language must still be "en" — the
        # attempted client-supplied "fr" must NOT have been persisted.
        assert _namespace(fake_db, namespace_id)["language"] == "en"


class TestRegistrationTimezone:
    """The registration router resolves the namespace `timezone` field
    server-side from `company.country` + `company.city` (see
    `src.app.core.geo_timezone.timezone_for_location`, called off the event
    loop via `run_in_threadpool`) and passes it into `create_account`."""

    def test_resolvable_country_and_city_persists_real_timezone(self, client, fake_db):
        res = client.post(
            REGISTER_URL, json=_payload(country="Tunisia", city="Tunis")
        )
        assert res.status_code == 201, res.text
        namespace_id = res.json()["data"]["namespace_id"]
        assert _namespace(fake_db, namespace_id)["timezone"] == "Africa/Tunis"

    def test_unresolvable_country_persists_none(self, client, fake_db):
        res = client.post(
            REGISTER_URL,
            json=_payload(country="Nowhereistan", city="Nowhereville"),
        )
        assert res.status_code == 201, res.text
        namespace_id = res.json()["data"]["namespace_id"]
        assert _namespace(fake_db, namespace_id)["timezone"] is None
