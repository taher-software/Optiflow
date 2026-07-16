import secrets
import uuid
from typing import Any

from fastapi import HTTPException, status

from src.app.core.firestore import USERS_COLLECTION, get_db
from src.app.core.security import hash_password
from src.app.globals.enum import EMAIL_REQUIRED_ROLES, Role

from src.app.routers.user.modelsIn import CreateUserIn, UpdateUserIn
from src.app.routers.user.modelsOut import UserOut

_MAX_CODE_ATTEMPTS = 100


def _to_out(user: dict[str, Any]) -> UserOut:
    return UserOut(
        id=user["id"],
        first_name=user.get("first_name", ""),
        last_name=user.get("last_name", ""),
        role=user.get("role", ""),
        email=user.get("email"),
        security_code=user.get("security_code", ""),
        namespace_id=user.get("namespace_id", ""),
    )


def _generate_security_code(db: Any, namespace_id: str) -> str:
    """Allocate a unique 4-digit security code within the namespace."""
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = f"{secrets.randbelow(10000):04d}"
        clash = (
            db.collection(USERS_COLLECTION)
            .where("namespace_id", "==", namespace_id)
            .where("security_code", "==", code)
            .limit(1)
            .get()
        )
        if not clash:
            return code
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not allocate a unique security code. Please retry.",
    )


def _assert_email_available(db: Any, email: str) -> None:
    existing = (
        db.collection(USERS_COLLECTION).where("email", "==", email).limit(1).get()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )


def create_user(payload: CreateUserIn, namespace_id: str) -> UserOut:
    db = get_db()

    if payload.email:
        _assert_email_available(db, str(payload.email))

    user_id = str(uuid.uuid4())
    code = _generate_security_code(db, namespace_id)
    doc = {
        "id": user_id,
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "role": payload.role.value,
        "email": str(payload.email) if payload.email else None,
        "password": hash_password(payload.password),
        "security_code": code,
        "namespace_id": namespace_id,
    }
    db.collection(USERS_COLLECTION).document(user_id).set(doc)
    return _to_out(doc)


def list_users(namespace_id: str) -> list[UserOut]:
    db = get_db()
    rows = (
        db.collection(USERS_COLLECTION)
        .where("namespace_id", "==", namespace_id)
        .get()
    )
    return [_to_out(r.to_dict() or {}) for r in rows]


def _load_scoped(db: Any, user_id: str, namespace_id: str) -> dict[str, Any]:
    snapshot = db.collection(USERS_COLLECTION).document(user_id).get()
    user = snapshot.to_dict() or {} if snapshot.exists else {}
    if not user or user.get("namespace_id") != namespace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    return user


def get_user(user_id: str, namespace_id: str) -> UserOut:
    return _to_out(_load_scoped(get_db(), user_id, namespace_id))


def update_user(user_id: str, payload: UpdateUserIn, namespace_id: str) -> UserOut:
    db = get_db()
    user = _load_scoped(db, user_id, namespace_id)

    if user.get("role") == Role.OWNER.value and payload.role is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The owner's role cannot be changed.",
        )

    updates: dict[str, Any] = {}
    if payload.first_name is not None:
        updates["first_name"] = payload.first_name
    if payload.last_name is not None:
        updates["last_name"] = payload.last_name
    if payload.role is not None:
        updates["role"] = payload.role.value
    if payload.email is not None and str(payload.email) != user.get("email"):
        _assert_email_available(db, str(payload.email))
        updates["email"] = str(payload.email)
    if payload.password:
        updates["password"] = hash_password(payload.password)

    # Enforce the email requirement against the resulting state.
    final_role = updates.get("role", user.get("role"))
    final_email = updates.get("email", user.get("email"))
    email_required = {r.value for r in EMAIL_REQUIRED_ROLES}
    if final_role in email_required and not final_email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email is required for admin, manager, and supervisor roles.",
        )

    if updates:
        db.collection(USERS_COLLECTION).document(user_id).update(updates)
    return _to_out({**user, **updates})
