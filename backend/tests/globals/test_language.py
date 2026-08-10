"""Unit tests for `src.app.globals.enum.language`: default-language
resolution from a free-text `country` field, and reading the `language`
field off a (possibly legacy, schemaless) namespace document."""

import pytest

from src.app.globals.enum.language import (
    FRENCH_DEFAULT_COUNTRIES,
    Language,
    language_of,
    resolve_default_language,
)


class TestResolveDefaultLanguage:
    @pytest.mark.parametrize(
        "country",
        ["Tunisia", "  tunisia ", "FRANCE", "france", "Canada", "Senegal"],
    )
    def test_french_list_country_resolves_to_fr(self, country):
        assert resolve_default_language(country) is Language.FR

    @pytest.mark.parametrize("country", ["Germany", "United States"])
    def test_non_french_list_country_resolves_to_en(self, country):
        assert resolve_default_language(country) is Language.EN

    def test_none_resolves_to_en(self):
        assert resolve_default_language(None) is Language.EN

    def test_blank_resolves_to_en(self):
        assert resolve_default_language("") is Language.EN

    def test_every_configured_country_round_trips_to_fr(self):
        # Guards against a future edit to the private country-name tuple
        # silently desyncing from the lookup set it's derived from.
        for country in FRENCH_DEFAULT_COUNTRIES:
            assert resolve_default_language(country) is Language.FR

    @pytest.mark.parametrize(
        "country",
        [
            "Belgique",
            "belgique",
            "Suisse",
            "  suisse ",
            "Algérie",
            "Algerie",
            "  côte d'ivoire  ",
            "Cote d'Ivoire",
            "Sénégal",
            "Senegal",
            "Cameroun",
            "Tchad",
            "Bénin",
            "Mauritanie",
            "Tunisie",
        ],
    )
    def test_french_exonym_or_accent_variant_resolves_to_fr(self, country):
        assert resolve_default_language(country) is Language.FR


class TestLanguageOf:
    def test_namespace_with_fr_language(self):
        assert language_of({"language": "fr"}) is Language.FR

    def test_namespace_with_en_language(self):
        assert language_of({"language": "en"}) is Language.EN

    def test_namespace_missing_language_field_defaults_to_en(self):
        # Regression case: legacy namespace documents predate this field
        # (Firestore is schemaless, no migrations) and must not raise.
        assert language_of({"id": "ns-1", "company_name": "Acme"}) is Language.EN

    def test_namespace_with_garbage_language_value_defaults_to_en(self):
        assert language_of({"language": "klingon"}) is Language.EN

    def test_none_namespace_defaults_to_en(self):
        assert language_of(None) is Language.EN

    def test_empty_namespace_defaults_to_en(self):
        assert language_of({}) is Language.EN
