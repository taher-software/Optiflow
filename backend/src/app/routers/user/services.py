import uuid
from typing import Any

from fastapi import HTTPException, status

from src.app.core.firestore import USERS_COLLECTION
from src.app.core.security import hash_password
from src.app.core.security_code import generate_security_code
from src.app.gcp import get_firestore_client
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import EMAIL_REQUIRED_ROLES, Role

from src.app.routers.user.modelsIn import CreateUserIn, UpdateUserIn
from src.app.routers.user.modelsOut import UserOut


def _to_out(user: dict[str, Any]) -> UserOut:
    return UserOut(
        id=user["id"],
        first_name=user.get("first_name", ""),
        last_name=user.get("last_name", ""),
        role=user.get("role", ""),
        email=user.get("email"),
        security_code=user.get("security_code", ""),
        namespace_id=user.get("namespace_id", ""),
        online=user.get("online", True),
    )


def _assert_email_available(client: FirestoreClient, email: str) -> None:
    existing = client.find_document(USERS_COLLECTION, {"email": email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )


def create_user(payload: CreateUserIn, namespace_id: str) -> UserOut:
    client = get_firestore_client()

    if payload.email:
        _assert_email_available(client, str(payload.email))

    user_id = str(uuid.uuid4())
    code = generate_security_code(client, namespace_id)
    doc = {
        "id": user_id,
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "role": payload.role.value,
        "email": str(payload.email) if payload.email else None,
        "password": hash_password(payload.password) if payload.password else None,
        "security_code": code,
        "namespace_id": namespace_id,
    }
    client.create_document(USERS_COLLECTION, doc, document_id=user_id)
    return _to_out(doc)


def list_users(namespace_id: str) -> list[UserOut]:
    client = get_firestore_client()
    rows = client.find_documents(USERS_COLLECTION, {"namespace_id": namespace_id})
    return [_to_out(r) for r in rows]


def _load_scoped(
    client: FirestoreClient, user_id: str, namespace_id: str
) -> dict[str, Any]:
    user = client.get_document(USERS_COLLECTION, user_id)
    if not user or user.get("namespace_id") != namespace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    return user


def get_user(user_id: str, namespace_id: str) -> UserOut:
    return _to_out(_load_scoped(get_firestore_client(), user_id, namespace_id))


def update_user(user_id: str, payload: UpdateUserIn, namespace_id: str) -> UserOut:
    client = get_firestore_client()
    user = _load_scoped(client, user_id, namespace_id)

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
        _assert_email_available(client, str(payload.email))
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

    # Enforce the password requirement against the resulting state too: an
    # email set with no password is a state `POST /users` already forbids
    # (`CreateUserIn`'s validator), so `PUT` must not be able to create it
    # either. Checked against the MERGED state (updates.get(...) or
    # user.get(...)), not the payload alone — a user who already has a
    # stored password must still be updatable with only a new email.
    final_password = updates.get("password", user.get("password"))
    if final_email and not final_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password is required when an email is set.",
        )

    if updates:
        client.update_document(USERS_COLLECTION, user_id, updates)
    return _to_out({**user, **updates})


def set_own_online(user: dict[str, Any], online: bool) -> UserOut:
    """Set the `online` flag on the CALLER's own document (self-service, no
    role check). Writes only the `online` key; every other field on the
    document is left untouched."""
    client = get_firestore_client()
    updates = {"online": online}
    client.update_document(USERS_COLLECTION, user["id"], updates)
    return _to_out({**user, **updates})
