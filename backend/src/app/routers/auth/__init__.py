from fastapi import APIRouter

from src.app.core.api_response import ApiResponse

from src.app.routers.auth import services
from src.app.routers.auth.modelsIn import LoginIn
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
