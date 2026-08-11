"""Expo push notifications.

Sends push notifications through the Expo push API to devices registered via
the mobile app's Expo push tokens.

Two different guarantees live here, deliberately:
- `send_push_notification` (singular) is fully defensive — it never raises.
  It is the low-level single-send primitive: a failed send is logged and
  swallowed, and it reports its outcome via a `bool` return instead.
- `send_push_notifications` (plural fan-out) is best-effort per token — one
  dead token must never fail the whole batch — BUT raises `PushDeliveryError`
  when EVERY token in a non-empty batch fails, so a total delivery outage is
  visible to the caller instead of silently swallowed. A batch with no valid
  tokens is a no-op, not a failure: nothing was attempted, so nothing failed.
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


class PushDeliveryError(Exception):
    """Raised by `send_push_notifications` when EVERY token in a non-empty
    batch failed to send — a total delivery outage, as opposed to an
    individual dead token (best-effort, not raised). Defined here (not in
    `async_jobs.exceptions`) because `core/` must not depend on the async
    layer; async handlers that want this classified as a retryable system
    failure let it propagate as-is (it is not a `FunctionalJobError`)."""


def send_push_notification(
    expo_push_token: str,
    title: str,
    message: str,
    notif_level: NotifLevel = "urgent",
    data: Optional[dict] = None,
) -> bool:
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
        `True` if the send succeeded, `False` on a caught failure or a
        missing token. Never raises: network errors, timeouts, and malformed
        responses from the Expo API are logged and swallowed here — this
        function stays the defensive single-send primitive. Its caller,
        `send_push_notifications`, is the one that turns a total-failure
        batch into a raised error.
    """
    if not expo_push_token:
        logger.info("send_push_notification: no device token provided, skipping.")
        return False

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
        return True
    except Exception as e:
        # Best-effort: never let a push failure propagate to the caller.
        logger.warning(f"send_push_notification: failed to send push notification: {e}")
        return False


def send_push_notifications(
    tokens: list[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
    notif_level: NotifLevel = "urgent",
) -> None:
    """
    Fan-out of `send_push_notification` over many device tokens.

    Best-effort PER TOKEN — one dead device must never fail the whole batch,
    so each send is attempted independently regardless of earlier failures.
    But NOT best-effort overall: if every token in a non-empty batch fails,
    that is a total delivery outage, not a partial degradation, and this
    function raises `PushDeliveryError` so the caller can react (e.g. an
    async job's `backoff` retry).

    Args:
        tokens: Expo push tokens to notify. `None`/empty tokens are skipped;
            if the resulting list is empty, this is a no-op.
        title: Notification title.
        body: Notification body text.
        data: Optional extra payload delivered to the app (e.g. a downtime
            ticket id used for deep-linking on tap).
        notif_level: Per-level Expo fields to apply to every message.

    Returns:
        None on success (including the no-valid-tokens no-op and a partial
        failure — the latter is logged as a warning naming the failure
        count).

    Raises:
        PushDeliveryError: every token in a non-empty `valid_tokens` batch
            failed to send.
    """
    valid_tokens = [t for t in (tokens or []) if t]
    if not valid_tokens:
        # Nothing was attempted (e.g. a namespace with no registered
        # devices) — normal, not an error. Never raise here.
        logger.info("send_push_notifications: no valid tokens, skipping.")
        return

    successes = 0
    for token in valid_tokens:
        if send_push_notification(token, title, body, notif_level=notif_level, data=data):
            successes += 1

    total = len(valid_tokens)
    if successes == 0:
        raise PushDeliveryError(
            f"send_push_notifications: all {total} push send(s) failed."
        )
    if successes < total:
        logger.warning(
            f"send_push_notifications: {total - successes} of {total} "
            "push send(s) failed."
        )
