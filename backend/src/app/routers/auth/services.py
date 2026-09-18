import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from src.app.core.firestore import (
    NAMESPACE_COLLECTION,
    PLAN_COLLECTION,
    TEMPORARY_CONNECTION_COLLECTION,
    USERS_COLLECTION,
)
from src.app.core.security import make_access_token, verify_password
from src.app.core.security_code import generate_security_code
from src.app.core.timezone import namespace_timezone
from src.app.gcp import get_firestore_client
from src.app.gcp.firestore import FirestoreClient
from src.app.routers.auth.modelsIn import CheckUserCodeIn, LoginIn, MobileLoginIn
from src.app.routers.auth.modelsOut import AuthUserOut, LoginOut

# Subscription expiry: below this many days expired the tenant only gets a
# warning; at or above it the base subscription is considered blocked.
_BLOCKED_AFTER_DAYS_EXPIRED = 30

# Device lockout on failed pairing attempts (`/auth/check-user-code`). A
# device is blocked after this many consecutive failed attempts, and the
# block lazily expires this long after the last attempt -- there is no
# scheduled job, expiry is only evaluated on the device's next attempt.
_LOCKOUT_THRESHOLD = 3
_LOCKOUT_WINDOW = timedelta(hours=1)
_LOCKOUT_MESSAGE = (
    "This device has been temporarily locked out after too many failed "
    "pairing attempts. Please wait about an hour before trying again."
)


def login(payload: LoginIn) -> LoginOut:
    """Authenticate a user by email + password and return an access token."""
    client = get_firestore_client()

    user = client.find_document(USERS_COLLECTION, {"email": payload.username})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    hashed = user.get("password")
    if not hashed:
        # Account exists but was never confirmed (no password set yet).
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please confirm your account before signing in.",
        )

    if not verify_password(payload.password, hashed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    return _build_login_out(user)


def _subscription_status(
    client: FirestoreClient, namespace_id: str
) -> tuple[Optional[bool], Optional[bool], Optional[str], Optional[str]]:
    """Compute the base subscription status shown on login:
    `(warning, blocked, plan_id, plan_name)`.

    Only the namespace's base subscription (`subscription_plan_id`,
    `subscription_end_date`) is considered -- every `extra_*` field and
    `oiu_generated` are ignored (those belong to the separate quota
    subscription, see `.claude/specs/subscription-plans.md`). A namespace
    with no base subscription yet (missing namespace or no end date) is
    blocked; a malformed end date resolves to `(None, None, ...)` for the
    warning/blocked pair -- this never fails the login.
    """
    namespace = client.get_document(NAMESPACE_COLLECTION, namespace_id)

    plan_id = (namespace or {}).get("subscription_plan_id")
    plan_name: Optional[str] = None
    if plan_id:
        plan = client.get_document(PLAN_COLLECTION, plan_id)
        plan_name = plan.get("name") if plan else None

    warning: Optional[bool] = None
    blocked: Optional[bool] = None
    end_date_raw = (namespace or {}).get("subscription_end_date")
    if not end_date_raw:
        # Never subscribed yet: blocked until a base subscription exists.
        warning, blocked = False, True
    else:
        try:
            end_date = date.fromisoformat(end_date_raw)
        except (TypeError, ValueError):
            end_date = None
        if end_date is not None:
            today = datetime.now(namespace_timezone(namespace_id, namespace)).date()
            days_expired = (today - end_date).days
            if days_expired >= _BLOCKED_AFTER_DAYS_EXPIRED:
                warning, blocked = False, True
            elif days_expired >= 1:
                warning, blocked = True, False
            # days_expired <= 0 (active, incl. the end date itself): both stay None.

    return warning, blocked, plan_id, plan_name


def _build_login_out(user: dict[str, Any]) -> LoginOut:
    client = get_firestore_client()
    token = make_access_token(
        {
            "user_id": user["id"],
            "namespace_id": user.get("namespace_id", ""),
            "role": user.get("role", ""),
        }
    )
    warning, blocked, plan_id, plan_name = _subscription_status(
        client, user.get("namespace_id", "")
    )
    return LoginOut(
        access_token=token,
        user=AuthUserOut(
            id=user["id"],
            email=user.get("email"),
            first_name=user.get("first_name", ""),
            last_name=user.get("last_name", ""),
            role=user.get("role", ""),
            namespace_id=user.get("namespace_id", ""),
            avatar_url=user.get("avatar_url"),
            online=user.get("online", True),
        ),
        warning=warning,
        blocked=blocked,
        plan_id=plan_id,
        plan_name=plan_name,
    )


def mobile_login(payload: MobileLoginIn) -> LoginOut:
    """Log in a mobile device already paired with a user account (via
    `device_id`), refreshing its push token if it changed."""
    client = get_firestore_client()

    user = client.find_document(USERS_COLLECTION, {"device_id": payload.device_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user is registered for this device.",
        )

    if payload.push_token and payload.push_token != user.get("push_token"):
        client.update_document(
            USERS_COLLECTION, user["id"], {"push_token": payload.push_token}
        )
        user["push_token"] = payload.push_token

    return _build_login_out(user)


def _lockout_expired(last_attempt_at: str | None) -> bool:
    """Whether a device's lockout window has elapsed since `last_attempt_at`
    (an ISO-8601 string, this codebase's timestamp convention). A missing/
    unparsable timestamp is treated as expired -- never as a permanent lock."""
    if not last_attempt_at:
        return True
    try:
        last = datetime.fromisoformat(last_attempt_at)
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last > _LOCKOUT_WINDOW


def _record_failed_attempt(
    client: FirestoreClient, device_id: str, lock_doc: dict[str, Any] | None
) -> None:
    """Increment (or start) the failed-attempt counter for `device_id`,
    blocking the device once `_LOCKOUT_THRESHOLD` consecutive failures are
    reached. `lock_doc` is the existing `temporary_connection` document (with
    its `id`), or `None` if the device has no prior record / its lockout just
    lazily expired."""
    trial_number = (lock_doc.get("trial_number", 0) if lock_doc else 0) + 1
    data = {
        "device_id": device_id,
        "trial_number": trial_number,
        "blocked": trial_number >= _LOCKOUT_THRESHOLD,
        "last_attempt_at": datetime.now(timezone.utc).isoformat(),
    }
    if lock_doc and lock_doc.get("id"):
        client.update_document(TEMPORARY_CONNECTION_COLLECTION, lock_doc["id"], data)
    else:
        # `device_id` is client-supplied and may contain characters Firestore
        # rejects in a document id (e.g. `/`), so it is stored as a field and
        # a generated id is used as the document key -- matches this
        # codebase's convention elsewhere (e.g. `user.services.create_user`).
        client.create_document(
            TEMPORARY_CONNECTION_COLLECTION, data, document_id=str(uuid.uuid4())
        )


def check_user_code(payload: CheckUserCodeIn) -> LoginOut:
    """Pair a mobile device with a user account identified by its current
    security code, then rotate the security code so it cannot be reused.

    A device that fails to pair 3 times in a row is temporarily locked out
    for an hour (lazily evaluated on its next attempt, no scheduled job): a
    blocked device gets 429 without even reaching the user lookup. A
    successful pairing clears any lockout record for the device.
    """
    client = get_firestore_client()
    device_id = payload.device_id
    security_code = payload.security_code.upper()

    lock_doc = client.find_document(
        TEMPORARY_CONNECTION_COLLECTION, {"device_id": device_id}
    )
    if lock_doc and lock_doc.get("blocked"):
        if not _lockout_expired(lock_doc.get("last_attempt_at")):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=_LOCKOUT_MESSAGE,
            )
        # Lockout window elapsed: this attempt proceeds and the counter
        # restarts from zero, reusing the same document.
        lock_doc = {**lock_doc, "trial_number": 0, "blocked": False}

    user = client.find_document(USERS_COLLECTION, {"security_code": security_code})
    if not user:
        _record_failed_attempt(client, device_id, lock_doc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user matches this security code.",
        )

    new_code = generate_security_code(client, user.get("namespace_id", ""))
    updates: dict[str, Any] = {
        "device_id": device_id,
        "security_code": new_code,
    }
    if payload.push_token:
        updates["push_token"] = payload.push_token
    client.update_document(USERS_COLLECTION, user["id"], updates)
    user.update(updates)

    if lock_doc and lock_doc.get("id"):
        client.delete_document(TEMPORARY_CONNECTION_COLLECTION, lock_doc["id"])

    return _build_login_out(user)
