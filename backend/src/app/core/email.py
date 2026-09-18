import html

from src.app.globals.enum import Language

from .config import get_settings

_PARA = "margin:0 0 16px;font-size:15px;line-height:1.6;color:#334155;"

# Per-language chrome strings for `_shell` (the "or copy this link" line and
# the footer tagline). The two existing senders (`send_confirmation_email`,
# `send_welcome_email`) rely on the `Language.FR` default to keep sending
# byte-identical French chrome — do not change that default.
_SHELL_CHROME: dict[Language, dict[str, str]] = {
    Language.FR: {
        "copy_link": "Ou copiez ce lien&nbsp;: ",
        "footer": "Operio — automatisez la gestion des arrêts machine et éradiquez leurs causes.",
    },
    Language.EN: {
        "copy_link": "Or copy this link: ",
        "footer": "Operio — automate machine-downtime management and eliminate its root causes.",
    },
}


def _shell(
    preheader: str,
    heading: str,
    body_html: str,
    cta_label: str,
    cta_url: str,
    language: Language = Language.FR,
) -> str:
    """Wrap email body content in a responsive, brand-styled HTML shell."""
    chrome = _SHELL_CHROME[language if language in _SHELL_CHROME else Language.FR]
    return f"""\
<!doctype html>
<html lang="{language.value}">
  <body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,Helvetica,sans-serif;">
    <span style="display:none;max-height:0;overflow:hidden;opacity:0;color:#f1f5f9;">{preheader}</span>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 12px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;">
          <tr><td style="background:#020617;padding:22px 32px;">
            <span style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;">Opti<span style="color:#2dd4bf;">Flow</span></span>
          </td></tr>
          <tr><td style="padding:32px;">
            <h1 style="margin:0 0 20px;font-size:21px;line-height:1.3;color:#0f172a;">{heading}</h1>
            {body_html}
            <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 4px;">
              <tr><td style="border-radius:12px;background:#0d9488;">
                <a href="{cta_url}" style="display:inline-block;padding:14px 30px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:12px;">{cta_label}</a>
              </td></tr>
            </table>
            <p style="margin:16px 0 0;font-size:12px;color:#94a3b8;word-break:break-all;">{chrome["copy_link"]}{cta_url}</p>
          </td></tr>
          <tr><td style="padding:20px 32px;background:#f8fafc;border-top:1px solid #e2e8f0;">
            <p style="margin:0;font-size:12px;line-height:1.5;color:#64748b;">{chrome["footer"]}</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def _send(to: str, subject: str, html: str) -> None:
    """Send an email through Resend. Imported lazily so the app module imports
    without the Resend SDK / API key being present."""
    import resend

    settings = get_settings()
    resend.api_key = settings.resend_api_key
    resend.Emails.send(
        {
            "from": settings.email_from,
            "to": [to],
            "subject": subject,
            "html": html,
        }
    )


def send_confirmation_email(to: str, confirm_url: str) -> None:
    body = (
        f'<p style="{_PARA}">Bienvenue sur <strong>Operio</strong>&nbsp;! Nous sommes '
        "ravis de vous compter parmi les usines qui reprennent le contrôle de leurs "
        "arrêts machine.</p>"
        f'<p style="{_PARA}">Il ne reste qu\'une étape&nbsp;: confirmez votre compte pour '
        "activer votre espace et commencer à piloter votre production en temps réel.</p>"
        f'<p style="{_PARA}">Ce lien est valable pendant 24&nbsp;heures.</p>'
    )
    html = _shell(
        "Confirmez votre compte Operio pour l'activer.",
        "Activez votre compte Operio",
        body,
        "Confirmer mon compte",
        confirm_url,
    )
    _send(to, "Confirmez votre compte Operio", html)


def send_welcome_email(to: str, username: str, password: str) -> None:
    app_url = get_settings().frontend_url
    body = (
        f'<p style="{_PARA}">Votre compte est confirmé et prêt à l\'emploi. Bienvenue '
        "dans Operio&nbsp;!</p>"
        f'<p style="{_PARA}">Voici vos identifiants de connexion&nbsp;:</p>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:0 0 16px;background:#f1f5f9;border-radius:12px;">'
        '<tr><td style="padding:16px 18px;font-size:14px;color:#0f172a;line-height:1.7;">'
        f"Identifiant&nbsp;: <strong>{username}</strong><br>"
        f'Mot de passe&nbsp;: <strong style="font-family:monospace;">{password}</strong>'
        "</td></tr></table>"
        f'<p style="{_PARA}">Pour votre sécurité, pensez à modifier votre mot de passe '
        "après votre première connexion.</p>"
    )
    html = _shell(
        "Votre compte Operio est prêt — voici vos identifiants.",
        "Votre compte est prêt 🎉",
        body,
        "Accéder à Operio",
        app_url,
    )
    _send(to, "Votre compte Operio est prêt", html)


_SUPERVISOR_EMAIL_COPY: dict[Language, dict[str, str]] = {
    Language.EN: {
        "subject": "Unknown-cause downtime at {location}",
        "heading": "A downtime was declared — cause unknown",
        "para1": "A downtime occurred at <strong>{location}</strong> for an unknown reason.",
        "para2": (
            "Please contact the production team on site to learn more about the "
            "issue, and follow the ticket through to closure in Operio."
        ),
        "cta": "Open Operio",
    },
    Language.FR: {
        "subject": "Arrêt de cause inconnue — {location}",
        "heading": "Un arrêt a été déclaré — cause inconnue",
        "para1": "Un arrêt s'est produit à <strong>{location}</strong> pour une raison inconnue.",
        "para2": (
            "Merci de contacter l'équipe de production sur place pour en savoir "
            "plus, et de suivre le ticket jusqu'à sa clôture dans Operio."
        ),
        "cta": "Ouvrir Operio",
    },
}


def send_down_time_supervisor_email(
    to: str, language: Language, location: str, app_url: str | None = None
) -> None:
    """Best-effort bilingual email alerting a production supervisor of an
    unknown-cause (`DownTimeType.OTHERS`) downtime ticket.

    `location` originates from tenant-entered workstation/line/UAP names, so
    it is HTML-escaped before being embedded in the body.
    """
    lang = language if language in _SUPERVISOR_EMAIL_COPY else Language.EN
    copy = _SUPERVISOR_EMAIL_COPY[lang]
    safe_location = html.escape(location)
    url = app_url or get_settings().frontend_url

    body = (
        f'<p style="{_PARA}">{copy["para1"].format(location=safe_location)}</p>'
        f'<p style="{_PARA}">{copy["para2"]}</p>'
    )
    rendered = _shell(
        copy["subject"].format(location=safe_location),
        copy["heading"],
        body,
        copy["cta"],
        url,
        language=lang,
    )
    _send(to, copy["subject"].format(location=safe_location), rendered)


_ESCALATION_EMAIL_COPY: dict[Language, dict[str, str]] = {
    Language.EN: {
        "subject": "Escalation — downtime unresolved for {duration}",
        "heading": "A downtime needs management attention",
        "para1": (
            "The downtime at <strong>{location}</strong> has been "
            "unresolved for <strong>{duration}</strong>."
        ),
        "para2": "Please follow up on this ticket in Operio.",
        "cta": "Open Operio",
    },
    Language.FR: {
        "subject": "Escalade — arrêt non résolu depuis {duration}",
        "heading": "Un arrêt requiert l'attention de la direction",
        "para1": (
            "L'arrêt à <strong>{location}</strong> n'est toujours pas "
            "résolu depuis <strong>{duration}</strong>."
        ),
        "para2": "Merci de suivre ce ticket dans Operio.",
        "cta": "Ouvrir Operio",
    },
}


def send_down_time_escalation_email(
    to: str, language: Language, location: str, duration: str, app_url: str | None = None
) -> None:
    """Best-effort bilingual email alerting management (manager, owner,
    production supervisor, process supervisor) that a downtime ticket has
    been unresolved for `duration` (elapsed since `created_at`).

    `location` and `duration` originate from tenant-entered data / formatted
    strings, so both are HTML-escaped before being embedded in the body —
    same posture as `send_down_time_supervisor_email`.
    """
    lang = language if language in _ESCALATION_EMAIL_COPY else Language.EN
    copy = _ESCALATION_EMAIL_COPY[lang]
    safe_location = html.escape(location)
    safe_duration = html.escape(duration)
    url = app_url or get_settings().frontend_url

    body = (
        f'<p style="{_PARA}">{copy["para1"].format(location=safe_location, duration=safe_duration)}</p>'
        f'<p style="{_PARA}">{copy["para2"]}</p>'
    )
    rendered = _shell(
        copy["subject"].format(location=safe_location, duration=safe_duration),
        copy["heading"],
        body,
        copy["cta"],
        url,
        language=lang,
    )
    _send(
        to,
        copy["subject"].format(location=safe_location, duration=safe_duration),
        rendered,
    )
