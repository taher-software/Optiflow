from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from itsdangerous import BadSignature, SignatureExpired

from src.app.core.firestore import USERS_COLLECTION, get_db
from src.app.core.security import read_access_token
from src.app.globals.enum import Role

_bearer = HTTPBearer(auto_error=False)


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

    snapshot = get_db().collection(USERS_COLLECTION).document(claims["user_id"]).get()
    if not snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found."
        )
    return snapshot.to_dict() or {}


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
