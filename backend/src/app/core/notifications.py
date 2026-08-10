"""Bilingual (en/fr) notification-copy registry for downtime tickets.

Pure, side-effect-free templates: no Firestore, no network, no I/O — just
text. Adding a language or a downtime-type variant is a data edit to the
dicts below, never a code change.

Two audiences:
  * `agent_notification`      — the process agent(s) responsible for a
    downtime ticket (e.g. "maintenance agent"). Picks a copy *variant* based
    on `down_time_type` via the explicit `_AGENT_VARIANT_BY_TYPE` mapping
    (`"others"`, `"wip_shortage"`, `"material_shortage"`; anything absent
    from the mapping falls back to `"default"`).
  * `supervisor_notification` — the production-supervisor alert sent only
    for `DownTimeType.OTHERS` (unknown-cause) tickets.
"""

from __future__ import annotations

from src.app.globals.enum import DownTimeType, Language, Process

# --- Localized process labels, used for the `{process}` placeholder in the
# agent "default" variant. ---
_PROCESS_LABELS: dict[Language, dict[Process, str]] = {
    Language.EN: {
        Process.PRODUCTION: "production",
        Process.MAINTENANCE: "maintenance",
        Process.QUALITY: "quality",
        Process.LOGISTIC: "logistics",
    },
    Language.FR: {
        Process.PRODUCTION: "production",
        Process.MAINTENANCE: "maintenance",
        Process.QUALITY: "qualité",
        Process.LOGISTIC: "logistique",
    },
}


def process_label(process: Process, language: Language) -> str:
    """Localized, human-readable label for a `Process`."""
    lang = language if language in _PROCESS_LABELS else Language.EN
    return _PROCESS_LABELS[lang][process]


# --- Agent notification templates, keyed by (language, variant). ---
# variant in {"default", "others", "wip_shortage", "material_shortage"}.
_AGENT_TEMPLATES: dict[Language, dict[str, tuple[str, str]]] = {
    Language.EN: {
        "default": (
            "New downtime ticket",
            "A new {process} downtime ticket needs attention at {location}.",
        ),
        "others": (
            "Downtime declared — unknown cause",
            "A downtime was declared at {location} for an unknown reason. "
            "Please monitor this issue and close it as soon as it is resolved.",
        ),
        "wip_shortage": (
            "WIP shortage — production stopped",
            "Production is stopped at {location} by a work-in-process shortage. "
            "Please work on the shortage and get production resumed as soon as "
            "possible.",
        ),
        "material_shortage": (
            "Material shortage — production stopped",
            "Production is stopped at {location} by a material / component "
            "shortage. Please supply the missing parts as soon as possible; "
            "the production team will close the ticket once production resumes.",
        ),
    },
    Language.FR: {
        "default": (
            "Nouvel arrêt déclaré",
            "Un nouvel arrêt {process} nécessite votre attention à {location}.",
        ),
        "others": (
            "Arrêt déclaré — cause inconnue",
            "Un arrêt a été déclaré à {location} pour une raison inconnue. Merci "
            "de suivre cet incident et de le clôturer dès qu'il est résolu.",
        ),
        "wip_shortage": (
            "Rupture d'en-cours — production arrêtée",
            "La production est arrêtée à {location} par une rupture d'en-cours "
            "(WIP). Merci de traiter la rupture et de faire reprendre la "
            "production dès que possible.",
        ),
        "material_shortage": (
            "Rupture matière — production arrêtée",
            "La production est arrêtée à {location} par une rupture matière / "
            "composant. Merci de fournir les pièces manquantes dès que "
            "possible ; l'équipe de production clôturera le ticket dès la "
            "reprise.",
        ),
    },
}

# Explicit `down_time_type -> variant` mapping (single source of truth), so
# it can never silently drift from `CLOSE_ONLY_DOWNTIME_TYPES` or from each
# other the way hand-written `if` branches could. Anything absent falls back
# to `"default"`.
_AGENT_VARIANT_BY_TYPE: dict[DownTimeType, str] = {
    DownTimeType.OTHERS: "others",
    DownTimeType.WIP_SHORTAGE: "wip_shortage",
    DownTimeType.MATERIAL_SHORTAGE: "material_shortage",
}


# --- Supervisor notification templates (OTHERS only), keyed by language. ---
_SUPERVISOR_TEMPLATES: dict[Language, tuple[str, str]] = {
    Language.EN: (
        "Unknown-cause downtime at {location}",
        "A downtime occurred at {location} for an unknown reason. Please "
        "contact the production team on site to learn more about the issue.",
    ),
    Language.FR: (
        "Arrêt de cause inconnue — {location}",
        "Un arrêt s'est produit à {location} pour une raison inconnue. Merci "
        "de contacter l'équipe de production sur place pour en savoir plus.",
    ),
}


def _agent_variant(down_time_type: DownTimeType) -> str:
    return _AGENT_VARIANT_BY_TYPE.get(down_time_type, "default")


def agent_notification(
    down_time_type: DownTimeType, process: Process, language: Language, location: str
) -> tuple[str, str]:
    """Build the (title, body) push copy for the process agent(s) responsible
    for a downtime ticket, localized to `language` and specialized by
    `down_time_type`. Unknown languages fall back to English."""
    lang = language if language in _AGENT_TEMPLATES else Language.EN
    variant = _agent_variant(down_time_type)
    title, body_template = _AGENT_TEMPLATES[lang][variant]
    body = body_template.format(
        process=process_label(process, lang), location=location
    )
    return title, body


def supervisor_notification(language: Language, location: str) -> tuple[str, str]:
    """Build the (title, body) push copy for the production-supervisor alert
    sent for `DownTimeType.OTHERS` (unknown-cause) tickets. Unknown languages
    fall back to English."""
    lang = language if language in _SUPERVISOR_TEMPLATES else Language.EN
    title_template, body_template = _SUPERVISOR_TEMPLATES[lang]
    return (
        title_template.format(location=location),
        body_template.format(location=location),
    )
