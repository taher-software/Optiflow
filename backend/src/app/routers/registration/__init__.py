from fastapi import APIRouter, status

from app.core.api_response import ApiResponse

from . import services
from .modelsIn import ConfirmAccountIn, RegisterAccountIn
from .modelsOut import ConfirmAccountOut, RegisterAccountOut

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
    result = services.create_account(payload)
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
