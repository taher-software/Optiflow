"""Offline country/city -> IANA timezone resolution, used at registration to
populate a namespace's `timezone` field.

No network call happens here — `geonamescache` ships a bundled dataset of
countries/cities and `timezonefinder` resolves a timezone from coordinates
using a bundled shapefile index. Both are safe to call from inside a request.

Accuracy caveat: for multi-zone countries (Canada, Russia, USA, ...) the
result is the *city's* zone when the city is recognized (accurate), or the
*country's capital* zone when only the country is known (an approximation —
the capital's offset does not necessarily match every workstation's actual
site). This is a sensible default for KPI timestamps, not ground truth.
"""

import logging
from functools import lru_cache
from typing import Optional

from src.app.globals.enum import fold_name

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_geonames_cache():
    """Lazily construct (and memoize) the `geonamescache.GeonamesCache`
    singleton. Building it costs ~0.8s — never do this at import time or per
    request."""
    import geonamescache

    return geonamescache.GeonamesCache()


@lru_cache(maxsize=1)
def _get_timezone_finder():
    """Lazily construct (and memoize) the `timezonefinder.TimezoneFinder`
    singleton. Building it costs ~0.8s — never do this at import time or per
    request."""
    from timezonefinder import TimezoneFinder

    return TimezoneFinder()


# Countries whose free-text `country` spelling may be given in French (the
# registration form is French-localized). Extra aliases beyond what
# `geonamescache` itself already recognizes, mapped to their ISO2 code.
# Only the francophone countries also listed in `language.py` need an alias
# here (an English/ISO name always resolves already via `_country_iso2_index`).
_FRENCH_COUNTRY_ALIASES: dict[str, str] = {
    "belgique": "BE",
    "suisse": "CH",
    "algerie": "DZ",
    "benin": "BJ",
    "cameroun": "CM",
    "republique centrafricaine": "CF",
    "tchad": "TD",
    "comores": "KM",
    "republique du congo": "CG",
    "republique democratique du congo": "CD",
    "guinee equatoriale": "GQ",
    "guinee": "GN",
    "cote d'ivoire": "CI",
    "mauritanie": "MR",
    "senegal": "SN",
    "tunisie": "TN",
}


@lru_cache(maxsize=1)
def _country_iso2_index() -> dict[str, str]:
    """Folded country-name -> ISO2 index built from `geonamescache`'s
    country list, plus French aliases for francophone tenants."""
    gc = _get_geonames_cache()
    index: dict[str, str] = {}
    for iso2, info in gc.get_countries().items():
        name = info.get("name")
        if name:
            index[fold_name(name)] = iso2
    index.update(_FRENCH_COUNTRY_ALIASES)
    return index


def _country_to_iso2(country: Optional[str]) -> Optional[str]:
    if not country:
        return None
    return _country_iso2_index().get(fold_name(country))


def warm_up() -> None:
    """Eagerly build the `GeonamesCache`/`TimezoneFinder` singletons and the
    derived country index.

    Meant to be called once, off the event loop (e.g.
    `asyncio.to_thread(warm_up)` from the FastAPI lifespan), so the ~1s
    construction cost never lands on a request — first call is ~1s, every
    later call is a no-op (the underlying accessors are memoized). Never
    raises: mirrors `timezone_for_location`'s own failure handling so a
    warm-up problem can never fail app startup.
    """
    try:
        _get_geonames_cache()
        _get_timezone_finder()
        _country_iso2_index()
    except Exception:
        logger.warning("geo_timezone.warm_up: failed to warm up geocoding singletons", exc_info=True)


def _search_matches(name: str) -> list[dict]:
    """Single `geonamescache.search_cities` scan for `name` (case-insensitive).
    This is the expensive call (~linear scan of the bundled city set) — every
    caller below reuses one scan's results rather than re-searching."""
    gc = _get_geonames_cache()
    return gc.search_cities(name, case_sensitive=False)


def _best_match(matches: list[dict], iso2: Optional[str]) -> Optional[dict]:
    """Pick the highest-population match, preferring ones in `iso2` when any
    of `matches` are in that country; otherwise the highest-population match
    across all countries. No further scanning — `matches` is already fetched."""
    if iso2:
        filtered = [m for m in matches if m.get("countrycode") == iso2]
        if filtered:
            matches = filtered
    if not matches:
        return None
    return max(matches, key=lambda m: m.get("population") or 0)


def _timezone_from_coordinates(latitude: float, longitude: float) -> Optional[str]:
    tf = _get_timezone_finder()
    return tf.timezone_at(lat=latitude, lng=longitude)


def timezone_for_location(country: Optional[str], city: Optional[str]) -> Optional[str]:
    """Resolve the IANA timezone for a free-text `country` + `city`.

    Resolution chain:
    1. `country` -> ISO2 (accent-folded; French exonyms like "Belgique" or
       "Tunisie" are recognized in addition to English/native names).
    2. `city` + ISO2 -> coordinates of the highest-population matching city
       in that country -> timezone.
    3. `city` with no match in that country (or country unknown) -> highest-
       population match across all countries -> timezone.
    4. Country known but city unknown/blank/unmatched -> the country's
       capital city -> timezone (see module docstring accuracy caveat).
    5. Nothing resolves -> `None`. Callers (registration) store `None` rather
       than inventing a zone; downstream readers already default to UTC.

    At most two `search_cities` scans are performed (one for `city`, one for
    the country's capital if step 2/3 didn't resolve) — each scan's results
    are reused for both the in-country and cross-country lookups instead of
    searching twice per step.

    Never raises: any lookup failure or unexpected library error is caught,
    logged at warning, and treated as "could not resolve".

    This is a CPU-bound call (~0.24s warm, ~1s cold while the singletons are
    built) — callers on the request path MUST run it off the event loop
    (e.g. `fastapi.concurrency.run_in_threadpool`), never `await` it directly
    from an `async def` route.
    """
    try:
        iso2 = _country_to_iso2(country)

        if city:
            match = _best_match(_search_matches(city), iso2)
            if match is not None:
                tz = _timezone_from_coordinates(match["latitude"], match["longitude"])
                if tz:
                    return tz

        if iso2:
            capital = _get_geonames_cache().get_countries().get(iso2, {}).get("capital")
            if capital:
                capital_match = _best_match(_search_matches(capital), iso2)
                if capital_match is not None:
                    tz = _timezone_from_coordinates(
                        capital_match["latitude"], capital_match["longitude"]
                    )
                    if tz:
                        return tz

        return None
    except Exception:
        logger.warning(
            "geo_timezone.timezone_for_location: failed to resolve timezone for "
            f"country={country!r} city={city!r}",
            exc_info=True,
        )
        return None
