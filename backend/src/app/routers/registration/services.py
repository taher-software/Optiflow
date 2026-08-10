import uuid

from fastapi import HTTPException, status
from itsdangerous import BadSignature, SignatureExpired

from src.app.core import email as email_service
from src.app.core.config import get_settings
from src.app.core.firestore import NAMESPACE_COLLECTION, USERS_COLLECTION
from src.app.core.security import (
    generate_password,
    hash_password,
    make_confirmation_token,
    read_confirmation_token,
)
from src.app.core.security_code import generate_security_code
from src.app.gcp import get_firestore_client
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import Role, resolve_default_language

from src.app.routers.registration.modelsIn import RegisterAccountIn
from src.app.routers.registration.modelsOut import ConfirmAccountOut, RegisterAccountOut, ResendConfirmationOut


def _safe_delete(client: FirestoreClient, collection_name: str, document_id: str) -> None:
    """Best-effort delete used to roll back partial writes (idempotency)."""
    try:
        client.delete_document(collection_name, document_id)
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


def create_account(payload: RegisterAccountIn, timezone: str | None) -> RegisterAccountOut:
    """Create a namespace (account) + owner user, then email a confirmation link.

    `timezone` is the namespace's IANA zone, pre-resolved by the router via
    `src.app.core.geo_timezone.timezone_for_location` (run off the event loop
    — see `routers.registration.__init__.register_account`) so this
    synchronous service function never does that CPU-bound work itself.
    `None` when it couldn't be resolved; stored as `None`, not `"UTC"` —
    downstream readers already default to UTC on a missing/blank value, and a
    stored `None` keeps "never resolved" distinguishable from "genuinely UTC".

    Atomic: if any write or the email fails, both documents are removed so the
    registration can be retried cleanly.
    """
    client = get_firestore_client()

    existing = client.find_document(
        USERS_COLLECTION, {"email": str(payload.owner.email)}
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    namespace_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    try:
        client.create_document(
            NAMESPACE_COLLECTION,
            {
                "id": namespace_id,
                "company_name": payload.company.company_name,
                "adress": payload.company.adress,
                "code_postal": payload.company.code_postal,
                "phone_number": payload.company.phone_number,
                "tax_identification_number": payload.company.tax_identification_number,
                "country": payload.company.country,
                "language": resolve_default_language(payload.company.country).value,
                "city": payload.company.city,
                "timezone": timezone,
                "confirmed": False,
            },
            document_id=namespace_id,
        )
        client.create_document(
            USERS_COLLECTION,
            {
                "id": user_id,
                "first_name": payload.owner.firstname,
                "last_name": payload.owner.lastname,
                "email": str(payload.owner.email),
                "avatar_url": payload.owner.avatar_url,
                "role": Role.OWNER.value,
                "password": None,  # set (hashed) only after account confirmation
                "namespace_id": namespace_id,
            },
            document_id=user_id,
        )
    except Exception as exc:
        _safe_delete(client, NAMESPACE_COLLECTION, namespace_id)
        _safe_delete(client, USERS_COLLECTION, user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create the account. Please retry.",
        ) from exc
    else:
        try:
            _send_confirmation(user_id, namespace_id, str(payload.owner.email))
        except Exception as exc:
            _safe_delete(client, NAMESPACE_COLLECTION, namespace_id)
            _safe_delete(client, USERS_COLLECTION, user_id)
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
    client = get_firestore_client()

    user = client.find_document(USERS_COLLECTION, {"email": str(email)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending account found for this email.",
        )

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

    namespace = client.get_document(NAMESPACE_COLLECTION, namespace_id) or {}
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
    client = get_firestore_client()

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

    namespace = client.get_document(NAMESPACE_COLLECTION, data["namespace_id"])
    if namespace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        )

    if namespace.get("confirmed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account has already been confirmed.",
        )

    user = client.get_document(USERS_COLLECTION, data["user_id"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Owner user not found."
        )
    if user.get("role") != Role.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the account owner can confirm the account.",
        )

    password = generate_password()
    security_code = generate_security_code(client, data["namespace_id"])
    client.update_document(
        USERS_COLLECTION,
        data["user_id"],
        {
            "password": hash_password(password),
            "security_code": security_code,
        },
    )
    client.update_document(NAMESPACE_COLLECTION, data["namespace_id"], {"confirmed": True})

    email_service.send_welcome_email(user["email"], user["email"], password)

    return ConfirmAccountOut(
        namespace_id=data["namespace_id"],
        email=user["email"],
        role=user.get("role", Role.OWNER.value),
    )
