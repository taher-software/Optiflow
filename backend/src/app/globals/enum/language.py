import unicodedata
from enum import Enum


class Language(str, Enum):
    """Primary language of a namespace (tenant).

    Drives which notification/email template version is used.
    """

    EN = "en"
    FR = "fr"


# Countries whose namespaces default to French, grouped the way the product
# spec listed them: metropolitan France + neighboring French-speaking Europe
# and North America first, then francophone Africa.
#
# Both the English name and its French exonym are listed for each country,
# since `country` is a free-text field on the registration form (rendered on
# a French-localized page) and operators may type either. Where the English
# and French spellings coincide, the name is listed once.
_FRENCH_DEFAULT_COUNTRY_NAMES: tuple[str, ...] = (
    # Europe / North America
    "France",
    "Monaco",
    "Belgium",
    "Belgique",
    "Switzerland",
    "Suisse",
    "Canada",
    "Luxembourg",
    # Francophone Africa
    "Algeria",
    "Algérie",
    "Benin",
    "Bénin",
    "Burkina Faso",
    "Burundi",
    "Cameroon",
    "Cameroun",
    "Central African Republic",
    "République centrafricaine",
    "Chad",
    "Tchad",
    "Comoros",
    "Comores",
    "Republic of the Congo",
    "République du Congo",
    "Democratic Republic of the Congo",
    "République démocratique du Congo",
    "Djibouti",
    "Equatorial Guinea",
    "Guinée équatoriale",
    "Gabon",
    "Guinea",
    "Guinée",
    "Ivory Coast",
    "Côte d'Ivoire",
    "Madagascar",
    "Mali",
    "Mauritania",
    "Mauritanie",
    "Niger",
    "Rwanda",
    "Senegal",
    "Sénégal",
    "Togo",
    "Tunisia",
    "Tunisie",
)


def _fold(value: str) -> str:
    """Normalize a free-text country name for lookup/comparison.

    Strips surrounding whitespace, lowercases, and folds accents/diacritics
    (NFKD-decompose then drop combining marks) so "Algérie" and "Algerie"
    — or "Côte d'Ivoire" and "cote d'ivoire" — compare equal. Used to build
    `FRENCH_DEFAULT_COUNTRIES` and to normalize lookups in
    `resolve_default_language`, so the two can never disagree.
    """
    decomposed = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


# Normalized (accent-folded, lowercased) lookup set derived from
# `_FRENCH_DEFAULT_COUNTRY_NAMES` via `_fold`.
FRENCH_DEFAULT_COUNTRIES: frozenset[str] = frozenset(
    _fold(name) for name in _FRENCH_DEFAULT_COUNTRY_NAMES
)


def resolve_default_language(country: str | None) -> Language:
    """Resolve the default namespace language from a free-text `country` field.

    Returns `Language.FR` when the country — accent-folded, stripped, and
    lowercased via `_fold` — is one of `FRENCH_DEFAULT_COUNTRIES`, otherwise
    `Language.EN`. Blank/None -> `Language.EN`.
    """
    if not country:
        return Language.EN
    if _fold(country) in FRENCH_DEFAULT_COUNTRIES:
        return Language.FR
    return Language.EN


def language_of(namespace: dict | None) -> Language:
    """Read the `language` field off a namespace Firestore document.

    Existing namespace documents predate this field (Firestore is schemaless
    — no migrations), so this defaults to `Language.EN` whenever the field is
    missing, blank, or not a valid `Language` value. Never raises.
    """
    if not namespace:
        return Language.EN
    value = namespace.get("language")
    if not value:
        return Language.EN
    try:
        return Language(value)
    except ValueError:
        return Language.EN
