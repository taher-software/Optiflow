"""Best-effort Expo push notifications.

Sends push notifications through the Expo push API to devices registered via
the mobile app's Expo push tokens. Fully defensive: this must never raise or
otherwise interrupt the caller's request/job — a failed push is simply
logged and swallowed, mirroring how `core/email.py` isolates its transactional
send from the caller.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def send_push_notifications(
    tokens: list[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> None:
    """
    Best-effort push notification send via the Expo push API.

    Args:
        tokens: Expo push tokens (e.g. `ExponentPushToken[xxxx]`) to notify.
            `None`/empty tokens are skipped; if the resulting list is empty,
            this is a no-op.
        title: Notification title.
        body: Notification body text.
        data: Optional extra payload delivered to the app (e.g. a downtime
            ticket id used for deep-linking on tap).

    Returns:
        None. Never raises: network errors, timeouts, and malformed
        responses from the Expo API are logged and swallowed so a push
        failure never breaks the calling request/job.
    """
    valid_tokens = [t for t in (tokens or []) if t]
    if not valid_tokens:
        logger.info("send_push_notifications: no valid tokens, skipping.")
        return

    messages = [
        {"to": token, "title": title, "body": body, "data": data or {}}
        for token in valid_tokens
    ]

    try:
        import httpx

        response = httpx.post(
            _EXPO_PUSH_URL,
            json=messages,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        logger.info(
            f"send_push_notifications: sent {len(messages)} message(s) to Expo push API."
        )
    except Exception as e:
        # Best-effort: never let a push failure propagate to the caller.
        logger.warning(f"send_push_notifications: failed to send push notifications: {e}")
