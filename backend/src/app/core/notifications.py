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
            "possible, then close this ticket.",
        ),
        "material_shortage": (
            "Material shortage — production stopped",
            "Production is stopped at {location} by a material / component "
            "shortage. Please acknowledge this ticket and supply the missing "
            "parts as soon as possible.",
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
            "production dès que possible, puis de clôturer ce ticket.",
        ),
        "material_shortage": (
            "Rupture matière — production arrêtée",
            "La production est arrêtée à {location} par une rupture matière / "
            "composant. Merci de prendre en charge ce ticket et de fournir les "
            "pièces manquantes dès que possible.",
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


# --- Downtime-ticket lifecycle-transition templates, keyed by (language,
# event). Used by the `notify_down_time_update` async job. ---
_LIFECYCLE_TEMPLATES: dict[Language, dict[str, tuple[str, str]]] = {
    Language.EN: {
        "acknowledged": (
            "Ticket acknowledged",
            "Your downtime ticket at {location} has been acknowledged and is "
            "being worked on.",
        ),
        "resolved": (
            "Ticket resolved",
            "Your downtime ticket at {location} has been resolved. Please "
            "check that production is back to normal, then close the ticket.",
        ),
        "rejected_resolver": (
            "Resolution rejected",
            "Production rejected your resolution of the downtime at "
            "{location}. The ticket is back in progress — please take "
            "another look.",
        ),
        "rejected_agents": (
            "Downtime still unresolved",
            "The downtime at {location} is still awaiting resolution — it "
            "has been open for {duration}.",
        ),
        "rejected_agents_generic": (
            "Downtime still unresolved",
            "The downtime at {location} is still awaiting resolution.",
        ),
    },
    Language.FR: {
        "acknowledged": (
            "Ticket pris en charge",
            "Votre arrêt déclaré à {location} a été pris en charge et est en "
            "cours de traitement.",
        ),
        "resolved": (
            "Ticket résolu",
            "Votre arrêt déclaré à {location} a été résolu. Merci de vérifier "
            "que la production est revenue à la normale, puis de clôturer le "
            "ticket.",
        ),
        "rejected_resolver": (
            "Résolution rejetée",
            "La production a rejeté votre résolution de l'arrêt à {location}. "
            "Le ticket est de nouveau en cours — merci de le réexaminer.",
        ),
        "rejected_agents": (
            "Arrêt toujours non résolu",
            "L'arrêt à {location} est toujours en attente de résolution — il "
            "est ouvert depuis {duration}.",
        ),
        "rejected_agents_generic": (
            "Arrêt toujours non résolu",
            "L'arrêt à {location} est toujours en attente de résolution.",
        ),
    },
}


def lifecycle_notification(
    event: str, language: Language, location: str, **kwargs
) -> tuple[str, str]:
    """Build the (title, body) push copy for a downtime-ticket lifecycle
    transition, localized to `language`. Unknown languages fall back to
    English, exactly like `agent_notification`/`supervisor_notification`.

    `event` selects the template variant: `"acknowledged"`, `"resolved"`,
    `"rejected_resolver"` (the responder whose resolution was rejected), or
    `"rejected_agents"` / `"rejected_agents_generic"` (every online process
    agent, with or without a `duration` string — see `format_duration`).
    Extra `**kwargs` (e.g. `duration=...`) are interpolated into the body
    template; unused keys are simply ignored by `str.format`.
    """
    lang = language if language in _LIFECYCLE_TEMPLATES else Language.EN
    title_template, body_template = _LIFECYCLE_TEMPLATES[lang][event]
    return (
        title_template.format(location=location, **kwargs),
        body_template.format(location=location, **kwargs),
    )


# --- Escalation templates, keyed by language. Used by the
# `escalate_down_time` async job (management alert, push + email). ---
_ESCALATION_TEMPLATES: dict[Language, tuple[str, str]] = {
    Language.EN: (
        "Escalation — downtime unresolved for {duration}",
        "The downtime at {location} has been unresolved for {duration} and "
        "needs management attention.",
    ),
    Language.FR: (
        "Escalade — arrêt non résolu depuis {duration}",
        "L'arrêt à {location} n'est toujours pas résolu depuis {duration} et "
        "requiert l'attention de la direction.",
    ),
}


def escalation_notification(
    language: Language, location: str, duration: str
) -> tuple[str, str]:
    """Build the (title, body) copy (push + email) alerting management that a
    downtime ticket has been unresolved for `duration`. Unknown languages
    fall back to English, exactly like the other notification builders."""
    lang = language if language in _ESCALATION_TEMPLATES else Language.EN
    title_template, body_template = _ESCALATION_TEMPLATES[lang]
    return (
        title_template.format(location=location, duration=duration),
        body_template.format(location=location, duration=duration),
    )


# --- Resolution-awaiting-confirmation template, keyed by language. Used by
# the `escalate_down_time` async job when a ticket is `resolved` and waiting
# on a production agent to confirm/reject it (push only). ---
_RESOLUTION_REMINDER_TEMPLATES: dict[Language, tuple[str, str]] = {
    Language.EN: (
        "Resolution awaiting your confirmation",
        "The downtime at {location} was marked resolved {duration} ago and "
        "is waiting on you. Please close it if production is back to "
        "normal, or reject the resolution.",
    ),
    Language.FR: (
        "Résolution en attente de votre confirmation",
        "L'arrêt à {location} a été marqué résolu il y a {duration} et "
        "attend votre confirmation. Merci de le clôturer si la production "
        "est revenue à la normale, ou de rejeter la résolution.",
    ),
}


def resolution_reminder_notification(
    language: Language, location: str, duration: str
) -> tuple[str, str]:
    """Build the (title, body) push copy reminding production agents to
    confirm/reject a resolved-but-unclosed downtime ticket. `duration` is the
    time elapsed since `resolved_at` (NOT `created_at` — unlike every other
    builder in this module). Unknown languages fall back to English."""
    lang = language if language in _RESOLUTION_REMINDER_TEMPLATES else Language.EN
    title_template, body_template = _RESOLUTION_REMINDER_TEMPLATES[lang]
    return (
        title_template.format(location=location, duration=duration),
        body_template.format(location=location, duration=duration),
    )


# --- Bilingual elapsed-duration formatter (pure, no I/O). ---
def format_duration(seconds: float, language: Language) -> str:
    """Render an elapsed duration in seconds as a short bilingual string:
    `"45m"` / `"2h 15m"` / `"3d 4h"` (EN) or `"45 min"` / `"2 h 15 min"` /
    `"3 j 4 h"` (FR). Negative/garbage input is clamped to 0. Pure — no I/O,
    never raises."""
    lang = language if language in (Language.EN, Language.FR) else Language.EN
    total_seconds = max(0, int(seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    if lang == Language.FR:
        if days:
            return f"{days} j {hours} h"
        if hours:
            return f"{hours} h {minutes} min"
        return f"{minutes} min"

    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
