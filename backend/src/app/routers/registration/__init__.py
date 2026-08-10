from fastapi import APIRouter, status
from fastapi.concurrency import run_in_threadpool

from src.app.core.api_response import ApiResponse
from src.app.core.geo_timezone import timezone_for_location

from src.app.routers.registration import services
from src.app.routers.registration.modelsIn import ConfirmAccountIn, RegisterAccountIn, ResendConfirmationIn
from src.app.routers.registration.modelsOut import ConfirmAccountOut, RegisterAccountOut, ResendConfirmationOut

router = APIRouter(prefix="/registration", tags=["registration"])


@router.post(
    "",
    response_model=ApiResponse[RegisterAccountOut],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new namespace (account)",
    description=(
        "Creates a new namespace (company) and its owner user in Firestore, then "
        "emails an account-confirmation link to the owner. The owner's password is "
        "only generated once the account is confirmed."
    ),
)
async def register_account(
    payload: RegisterAccountIn,
) -> ApiResponse[RegisterAccountOut]:
    # `timezone_for_location` is CPU-bound (offline geocoding, up to ~1s cold
    # / ~0.24s warm) — run it in Starlette's threadpool so it never blocks
    # the event loop and stalls co-resident requests on this instance.
    timezone = await run_in_threadpool(
        timezone_for_location, payload.company.country, payload.company.city
    )
    result = services.create_account(payload, timezone)
    return ApiResponse(
        message="Confirmation email sent. Please confirm to activate the account.",
        data=result,
    )


@router.post(
    "/confirm",
    response_model=ApiResponse[ConfirmAccountOut],
    summary="Confirm the account and finalize it",
    description=(
        "Confirms the account using the token from the confirmation link. "
        "Generates the owner's password, stores it hashed, marks the account "
        "confirmed, and emails the credentials + a welcome message."
    ),
)
async def confirm_account(payload: ConfirmAccountIn) -> ApiResponse[ConfirmAccountOut]:
    result = services.confirm_account(payload.token)
    return ApiResponse(
        message="Account confirmed. Credentials have been sent by email.",
        data=result,
    )


@router.post(
    "/resend",
    response_model=ApiResponse[ResendConfirmationOut],
    summary="Resend the account-confirmation email",
    description=(
        "Resends the confirmation email for a still-unconfirmed account (e.g. after "
        "the link expired). Returns 404 if no pending account matches the email, 403 "
        "if the user is not the account owner, and 409 if the account is already "
        "confirmed."
    ),
)
async def resend_confirmation(
    payload: ResendConfirmationIn,
) -> ApiResponse[ResendConfirmationOut]:
    result = services.resend_confirmation(payload.email)
    return ApiResponse(
        message="Confirmation email resent.",
        data=result,
    )
