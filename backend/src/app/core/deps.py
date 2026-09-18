import hmac
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from itsdangerous import BadSignature, SignatureExpired

from src.app.core.config import get_settings
from src.app.core.firestore import USERS_COLLECTION
from src.app.core.security import read_access_token
from src.app.gcp import get_firestore_client
from src.app.globals.enum import Role

_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Resolve the authenticated user from the bearer access token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated."
        )
    try:
        claims = read_access_token(credentials.credentials)
    except (SignatureExpired, BadSignature) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        ) from exc

    client = get_firestore_client()
    user = client.get_document(USERS_COLLECTION, claims["user_id"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found."
        )
    return user


def require_roles(*roles: Role) -> Callable[..., dict]:
    """Dependency factory: allow only users whose role is in `roles`."""
    allowed = {role.value for role in roles}

    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return checker


def require_api_key(api_key: str | None = Depends(_api_key_header)) -> None:
    """Platform-level auth for back-office endpoints (`/plans`,
    `/subscriptions`): a static key sent via `X-API-Key`, compared in
    constant time. Not a substitute for, nor combinable with, a user bearer
    token — these endpoints are never called by tenant users.

    Fails closed: an unconfigured (empty) `platform_api_key` setting rejects
    every request rather than accepting an empty key.
    """
    configured = get_settings().platform_api_key
    if not configured or not api_key or not hmac.compare_digest(api_key, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
