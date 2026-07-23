"""Best-effort Expo push notifications.

Sends push notifications through the Expo push API to devices registered via
the mobile app's Expo push tokens. Fully defensive: this must never raise or
otherwise interrupt the caller's request/job — a failed push is simply
logged and swallowed, mirroring how `core/email.py` isolates its transactional
send from the caller.
"""

import logging
from typing import Literal, Optional

import requests

logger = logging.getLogger(__name__)

_EXPO_PUSH_URL = "https://api.expo.dev/v2/push/send?useFcmV1=true"

NotifLevel = Literal["urgent", "standard"]

# Per-level Expo message fields spread into every push payload. `channelId`
# selects the Android notification channel; `priority`/`sound` drive how
# intrusively the OS surfaces it.
notif_type: dict[str, dict] = {
    "standard": dict(channelId="standard", sound="standard.wav"),
    "urgent": dict(channelId="urgent", sound="urgent.wav"),
}


def send_push_notification(
    expo_push_token: str,
    title: str,
    message: str,
    notif_level: NotifLevel = "urgent",
    data: Optional[dict] = None,
) -> None:
    """
    Best-effort push notification send to a single device via the Expo push API.

    Args:
        expo_push_token: Expo push token (e.g. `ExponentPushToken[xxxx]`) to
            notify. A falsy token is skipped (no-op).
        title: Notification title.
        message: Notification body text.
        notif_level: Selects the per-level Expo fields (priority / sound /
            channel) from `notif_type`. Defaults to "urgent".
        data: Optional extra payload delivered to the app (e.g. a downtime
            ticket id used for deep-linking on tap).

    Returns:
        None. Never raises: network errors, timeouts, and malformed responses
        from the Expo API are logged and swallowed so a push failure never
        breaks the calling request/job.
    """
    if not expo_push_token:
        logger.info("send_push_notification: no device token provided, skipping.")
        return

    payload = {
        "to": expo_push_token,
        "title": title,
        "body": message,
        "data": data or {},
        **notif_type[notif_level],
    }

    try:
        response = requests.post(
            _EXPO_PUSH_URL,
            json=payload,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        logger.info("send_push_notification: sent 1 message to Expo push API.")
    except Exception as e:
        # Best-effort: never let a push failure propagate to the caller.
        logger.warning(f"send_push_notification: failed to send push notification: {e}")


def send_push_notifications(
    tokens: list[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
    notif_level: NotifLevel = "urgent",
) -> None:
    """
    Best-effort fan-out of `send_push_notification` over many device tokens.

    Args:
        tokens: Expo push tokens to notify. `None`/empty tokens are skipped;
            if the resulting list is empty, this is a no-op.
        title: Notification title.
        body: Notification body text.
        data: Optional extra payload delivered to the app (e.g. a downtime
            ticket id used for deep-linking on tap).
        notif_level: Per-level Expo fields to apply to every message.

    Returns:
        None. Each send is independently best-effort and never raises.
    """
    valid_tokens = [t for t in (tokens or []) if t]
    if not valid_tokens:
        logger.info("send_push_notifications: no valid tokens, skipping.")
        return

    for token in valid_tokens:
        send_push_notification(token, title, body, notif_level=notif_level, data=data)
