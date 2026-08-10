"""Tests for `src.app.core.geo_timezone.timezone_for_location`.

Offline geocoding (no network): `geonamescache` + `timezonefinder` resolve a
free-text country/city to an IANA timezone name, or `None` when it cannot be
determined — callers (registration) then leave the field unset rather than
inventing a zone.
"""

from src.app.core.geo_timezone import timezone_for_location


class TestTimezoneForLocationKnownCities:
    def test_tunisia_tunis(self):
        assert timezone_for_location("Tunisia", "Tunis") == "Africa/Tunis"

    def test_france_lyon(self):
        assert timezone_for_location("France", "Lyon") == "Europe/Paris"

    def test_canada_vancouver(self):
        tz = timezone_for_location("Canada", "Vancouver")
        assert tz is not None
        assert tz.startswith("America/")
        assert tz == "America/Vancouver"

    def test_canada_montreal_is_a_different_america_zone(self):
        """Montreal maps to America/Toronto in the geonames dataset — same
        UTC offset as Montreal, different city name. Assert the prefix only,
        not the exact zone name."""
        tz = timezone_for_location("Canada", "Montreal")
        assert tz is not None
        assert tz.startswith("America/")


class TestTimezoneForLocationFrenchCountryNames:
    def test_tunisie_alias(self):
        assert timezone_for_location("Tunisie", "Tunis") == "Africa/Tunis"

    def test_belgique_alias(self):
        tz = timezone_for_location("Belgique", "Brussels")
        assert tz is not None
        assert tz.startswith("Europe/")


class TestTimezoneForLocationCapitalFallback:
    def test_unknown_city_falls_back_to_country_capital(self):
        """City is unrecognized but the country is known: falls back to the
        country's capital city's zone."""
        tz = timezone_for_location("Tunisia", "Nonexistentcityxyz123")
        assert tz == "Africa/Tunis"  # Tunis is also Tunisia's capital

    def test_blank_city_falls_back_to_country_capital(self):
        assert timezone_for_location("France", "") == "Europe/Paris"


class TestTimezoneForLocationUnresolvable:
    def test_garbage_country_and_city_returns_none(self):
        assert timezone_for_location("Nowhereistan", "Nowhereville") is None

    def test_none_inputs_return_none(self):
        assert timezone_for_location(None, None) is None

    def test_blank_inputs_return_none(self):
        assert timezone_for_location("", "") is None

    def test_none_country_with_blank_city_returns_none(self):
        assert timezone_for_location(None, "") is None
