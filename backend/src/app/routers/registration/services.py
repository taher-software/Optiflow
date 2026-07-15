import uuid
from typing import Any

from fastapi import HTTPException, status
from itsdangerous import BadSignature, SignatureExpired

from src.app.core import email as email_service
from src.app.core.config import get_settings
from src.app.core.firestore import NAMESPACE_COLLECTION, USERS_COLLECTION, get_db
from src.app.core.security import (
    generate_password,
    hash_password,
    make_confirmation_token,
    read_confirmation_token,
)
from src.app.globals.enum import Role

from src.app.routers.registration.modelsIn import RegisterAccountIn
from src.app.routers.registration.modelsOut import ConfirmAccountOut, RegisterAccountOut, ResendConfirmationOut


def _safe_delete(ref: Any) -> None:
    """Best-effort delete used to roll back partial writes (idempotency)."""
    try:
        ref.delete()
    except Exception:
        pass


def _send_confirmation(user_id: str, namespace_id: str, email: str) -> None:
    """Build the confirmation link and send the confirmation email.

    Shared by registration and resend so the email communication stays consistent.
    """
    settings = get_settings()
    token = make_confirmation_token({"user_id": user_id, "namespace_id": namespace_id})
    confirm_url = f"{settings.frontend_url.rstrip('/')}/confirm-account?token={token}"
    email_service.send_confirmation_email(email, confirm_url)


def create_account(payload: RegisterAccountIn) -> RegisterAccountOut:
    """Create a namespace (account) + owner user, then email a confirmation link.

    Atomic: if any write or the email fails, both documents are removed so the
    registration can be retried cleanly.
    """
    db = get_db()

    existing = (
        db.collection(USERS_COLLECTION)
        .where("email", "==", str(payload.owner.email))
        .limit(1)
        .get()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    namespace_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    namespace_ref = db.collection(NAMESPACE_COLLECTION).document(namespace_id)
    user_ref = db.collection(USERS_COLLECTION).document(user_id)

    try:
        namespace_ref.set(
            {
                "id": namespace_id,
                "company_name": payload.company.company_name,
                "adress": payload.company.adress,
                "code_postal": payload.company.code_postal,
                "phone_number": payload.company.phone_number,
                "tax_identification_number": payload.company.tax_identification_number,
                "country": payload.company.country,
                "city": payload.company.city,
                "confirmed": False,
            }
        )
        user_ref.set(
            {
                "id": user_id,
                "firstname": payload.owner.firstname,
                "lastname": payload.owner.lastname,
                "email": str(payload.owner.email),
                "avatar_url": payload.owner.avatar_url,
                "role": Role.OWNER.value,
                "password": None,  # set (hashed) only after account confirmation
                "namespace_id": namespace_id,
            }
        )
    except Exception as exc:
        _safe_delete(namespace_ref)
        _safe_delete(user_ref)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create the account. Please retry.",
        ) from exc
    else:
        try:
            _send_confirmation(user_id, namespace_id, str(payload.owner.email))
        except Exception as exc:
            _safe_delete(namespace_ref)
            _safe_delete(user_ref)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not send the confirmation email. Please retry.",
            ) from exc

    return RegisterAccountOut(namespace_id=namespace_id, email=payload.owner.email)


def resend_confirmation(email: str) -> ResendConfirmationOut:
    """Resend the confirmation email for a still-unconfirmed account.

    Returns a generic result regardless of whether an account exists / is already
    confirmed, to avoid leaking which emails are registered.
    """
    db = get_db()

    matches = (
        db.collection(USERS_COLLECTION).where("email", "==", str(email)).limit(1).get()
    )
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending account found for this email.",
        )

    user = matches[0].to_dict() or {}
    if user.get("role") != Role.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the account owner can request a confirmation email.",
        )

    namespace_id = user.get("namespace_id")
    if not namespace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending account found for this email.",
        )

    namespace_snap = db.collection(NAMESPACE_COLLECTION).document(namespace_id).get()
    namespace = namespace_snap.to_dict() or {} if namespace_snap.exists else {}
    if namespace.get("confirmed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account has already been confirmed.",
        )

    _send_confirmation(user["id"], namespace_id, user["email"])
    return ResendConfirmationOut(email=email)


def confirm_account(token: str) -> ConfirmAccountOut:
    """Confirm an account: validate the token, generate + hash the owner's
    password, mark the account (namespace) confirmed, and email the credentials.
    """
    db = get_db()

    try:
        data = read_confirmation_token(token)
    except SignatureExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation link has expired.",
        ) from exc
    except BadSignature as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid confirmation link.",
        ) from exc

    namespace_ref = db.collection(NAMESPACE_COLLECTION).document(data["namespace_id"])
    namespace_snap = namespace_ref.get()
    if not namespace_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        )

    namespace = namespace_snap.to_dict() or {}
    if namespace.get("confirmed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account has already been confirmed.",
        )

    user_ref = db.collection(USERS_COLLECTION).document(data["user_id"])
    user_snap = user_ref.get()
    if not user_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Owner user not found."
        )
    user = user_snap.to_dict() or {}
    if user.get("role") != Role.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the account owner can confirm the account.",
        )

    password = generate_password()
    user_ref.update({"password": hash_password(password)})
    namespace_ref.update({"confirmed": True})

    email_service.send_welcome_email(user["email"], user["email"], password)

    return ConfirmAccountOut(
        namespace_id=data["namespace_id"],
        email=user["email"],
        role=user.get("role", Role.OWNER.value),
    )
