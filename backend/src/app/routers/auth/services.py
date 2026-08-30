from typing import Any

from fastapi import HTTPException, status

from src.app.core.firestore import USERS_COLLECTION
from src.app.core.security import make_access_token, verify_password
from src.app.core.security_code import generate_security_code
from src.app.gcp import get_firestore_client

from src.app.routers.auth.modelsIn import CheckUserCodeIn, LoginIn, MobileLoginIn
from src.app.routers.auth.modelsOut import AuthUserOut, LoginOut


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


def _build_login_out(user: dict[str, Any]) -> LoginOut:
    token = make_access_token(
        {
            "user_id": user["id"],
            "namespace_id": user.get("namespace_id", ""),
            "role": user.get("role", ""),
        }
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


def check_user_code(payload: CheckUserCodeIn) -> LoginOut:
    """Pair a mobile device with a user account identified by its current
    security code, then rotate the security code so it cannot be reused."""
    client = get_firestore_client()

    user = client.find_document(
        USERS_COLLECTION, {"security_code": payload.security_code}
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user matches this security code.",
        )

    new_code = generate_security_code(client, user.get("namespace_id", ""))
    updates: dict[str, Any] = {
        "device_id": payload.device_id,
        "security_code": new_code,
    }
    if payload.push_token:
        updates["push_token"] = payload.push_token
    client.update_document(USERS_COLLECTION, user["id"], updates)
    user.update(updates)

    return _build_login_out(user)
