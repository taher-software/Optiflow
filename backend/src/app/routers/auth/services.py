from fastapi import HTTPException, status

from src.app.core.firestore import USERS_COLLECTION, get_db
from src.app.core.security import make_access_token, verify_password

from src.app.routers.auth.modelsIn import LoginIn
from src.app.routers.auth.modelsOut import AuthUserOut, LoginOut


def login(payload: LoginIn) -> LoginOut:
    """Authenticate a user by email + password and return an access token."""
    db = get_db()

    matches = (
        db.collection(USERS_COLLECTION)
        .where("email", "==", payload.username)
        .limit(1)
        .get()
    )
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    user = matches[0].to_dict() or {}
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
            email=user["email"],
            first_name=user.get("first_name", ""),
            last_name=user.get("last_name", ""),
            role=user.get("role", ""),
            namespace_id=user.get("namespace_id", ""),
            avatar_url=user.get("avatar_url"),
        ),
    )
