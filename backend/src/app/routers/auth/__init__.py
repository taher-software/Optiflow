from fastapi import APIRouter

from src.app.core.api_response import ApiResponse

from src.app.routers.auth import services
from src.app.routers.auth.modelsIn import CheckUserCodeIn, LoginIn, MobileLoginIn
from src.app.routers.auth.modelsOut import LoginOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=ApiResponse[LoginOut],
    summary="Log in with username and password",
    description=(
        "Authenticates a user by their username (email) and password. On success "
        "returns a bearer access token to be sent as `Authorization: Bearer <token>` "
        "on subsequent requests. Returns 401 for invalid credentials and 403 if the "
        "account has not been confirmed yet."
    ),
)
async def login(payload: LoginIn) -> ApiResponse[LoginOut]:
    result = services.login(payload)
    return ApiResponse(message="Login successful.", data=result)


@router.post(
    "/mobile-login",
    response_model=ApiResponse[LoginOut],
    summary="Log in from an already-paired mobile device",
    description=(
        "Authenticates a mobile device previously paired with a user account "
        "(see `/auth/check-user-code`), identified by its `device_id`. On success "
        "returns a bearer access token to be sent as `Authorization: Bearer <token>` "
        "on subsequent requests. If a `push_token` is supplied and differs from the "
        "one on file, it replaces it. Returns 404 if no user is registered for the "
        "given device."
    ),
    responses={
        404: {"description": "No user is registered for this device."},
    },
)
async def mobile_login(payload: MobileLoginIn) -> ApiResponse[LoginOut]:
    result = services.mobile_login(payload)
    return ApiResponse(message="Login successful.", data=result)


@router.post(
    "/check-user-code",
    response_model=ApiResponse[LoginOut],
    summary="Pair a mobile device using a user's security code",
    description=(
        "Looks up a user by their current 4-digit `security_code`, pairs the given "
        "`device_id` (and optional `push_token`) with that account, and rotates the "
        "security code to a new unique value so the one just used cannot be reused. "
        "On success returns a bearer access token to be sent as "
        "`Authorization: Bearer <token>` on subsequent requests, and the paired "
        "device can subsequently use `/auth/mobile-login`. Returns 404 if no user "
        "matches the given security code."
    ),
    responses={
        404: {"description": "No user matches this security code."},
    },
)
async def check_user_code(payload: CheckUserCodeIn) -> ApiResponse[LoginOut]:
    result = services.check_user_code(payload)
    return ApiResponse(message="Device paired successfully.", data=result)
