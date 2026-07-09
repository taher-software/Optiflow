from .config import get_settings

_PARA = "margin:0 0 16px;font-size:15px;line-height:1.6;color:#334155;"


def _shell(
    preheader: str, heading: str, body_html: str, cta_label: str, cta_url: str
) -> str:
    """Wrap email body content in a responsive, brand-styled HTML shell."""
    return f"""\
<!doctype html>
<html lang="fr">
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
            <p style="margin:16px 0 0;font-size:12px;color:#94a3b8;word-break:break-all;">Ou copiez ce lien&nbsp;: {cta_url}</p>
          </td></tr>
          <tr><td style="padding:20px 32px;background:#f8fafc;border-top:1px solid #e2e8f0;">
            <p style="margin:0;font-size:12px;line-height:1.5;color:#64748b;">OptiFlow — automatisez la gestion des arrêts machine et éradiquez leurs causes.</p>
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
        f'<p style="{_PARA}">Bienvenue sur <strong>OptiFlow</strong>&nbsp;! Nous sommes '
        "ravis de vous compter parmi les usines qui reprennent le contrôle de leurs "
        "arrêts machine.</p>"
        f'<p style="{_PARA}">Il ne reste qu\'une étape&nbsp;: confirmez votre compte pour '
        "activer votre espace et commencer à piloter votre production en temps réel.</p>"
        f'<p style="{_PARA}">Ce lien est valable pendant 24&nbsp;heures.</p>'
    )
    html = _shell(
        "Confirmez votre compte OptiFlow pour l'activer.",
        "Activez votre compte OptiFlow",
        body,
        "Confirmer mon compte",
        confirm_url,
    )
    _send(to, "Confirmez votre compte OptiFlow", html)


def send_welcome_email(to: str, username: str, password: str) -> None:
    app_url = get_settings().frontend_url
    body = (
        f'<p style="{_PARA}">Votre compte est confirmé et prêt à l\'emploi. Bienvenue '
        "dans OptiFlow&nbsp;!</p>"
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
        "Votre compte OptiFlow est prêt — voici vos identifiants.",
        "Votre compte est prêt 🎉",
        body,
        "Accéder à OptiFlow",
        app_url,
    )
    _send(to, "Votre compte OptiFlow est prêt", html)
