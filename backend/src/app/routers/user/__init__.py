from fastapi import APIRouter, Depends, status

from src.app.core.api_response import ApiResponse
from src.app.core.deps import get_current_user, require_roles
from src.app.globals.enum import Role

from src.app.routers.user import services
from src.app.routers.user.modelsIn import CreateUserIn, SetOnlineIn, UpdateUserIn
from src.app.routers.user.modelsOut import UserOut

router = APIRouter(prefix="/users", tags=["users"])

# Only owners and admins may manage users.
_admin_or_owner = require_roles(Role.OWNER, Role.ADMIN)


@router.patch(
    "/me/online",
    response_model=ApiResponse[UserOut],
    status_code=status.HTTP_200_OK,
    summary="Set my own online/offline reachability",
    description=(
        "Self-service: any authenticated user may declare themselves online or "
        "offline for team push notifications. Idempotent — repeating the same "
        "value is a no-op and never errors. Identity comes only from the "
        "bearer token; no user id may be passed in the path or body, so a "
        "caller can never modify anyone else's account, in this tenant or "
        "another. Declaring yourself offline does not silence supervisor "
        "escalations, only team-level notifications.\n\n"
        "NOTE: declared BEFORE `/{user_id}` so `me` is never captured as a "
        "user id by the routes below."
    ),
)
async def set_own_online(
    payload: SetOnlineIn,
    current: dict = Depends(get_current_user),
) -> ApiResponse[UserOut]:
    result = services.set_own_online(current, payload.online)
    return ApiResponse(message="Online status updated.", data=result)


@router.post(
    "",
    response_model=ApiResponse[UserOut],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description=(
        "Creates a user in the caller's namespace and allocates a unique 4-digit "
        "security code. Restricted to owner/admin. The owner role cannot be "
        "assigned; email is required for admin, manager, and supervisor roles.\n\n"
        "`password` is required whenever `email` is set (directly, or "
        "transitively because the role requires an email) and optional "
        "otherwise. A user created with no email and no password cannot sign "
        "in via `POST /auth/login` (which requires a password hash); the "
        "mobile app is the only way in for that user, pairing a device with "
        "the allocated security code via `POST /auth/check-user-code`."
    ),
)
async def create_user(
    payload: CreateUserIn,
    current: dict = Depends(_admin_or_owner),
) -> ApiResponse[UserOut]:
    result = services.create_user(payload, current["namespace_id"])
    return ApiResponse(message="User created.", data=result)


@router.get(
    "",
    response_model=ApiResponse[list[UserOut]],
    summary="List users",
    description="Lists all users in the caller's namespace. Restricted to owner/admin.",
)
async def list_users(
    current: dict = Depends(_admin_or_owner),
) -> ApiResponse[list[UserOut]]:
    return ApiResponse(data=services.list_users(current["namespace_id"]))


@router.get(
    "/{user_id}",
    response_model=ApiResponse[UserOut],
    summary="Get a user",
    description="Fetches one user (with its security code). Restricted to owner/admin.",
)
async def get_user(
    user_id: str,
    current: dict = Depends(_admin_or_owner),
) -> ApiResponse[UserOut]:
    return ApiResponse(data=services.get_user(user_id, current["namespace_id"]))


@router.put(
    "/{user_id}",
    response_model=ApiResponse[UserOut],
    summary="Update a user",
    description="Updates a user in the caller's namespace. Restricted to owner/admin.",
)
async def update_user(
    user_id: str,
    payload: UpdateUserIn,
    current: dict = Depends(_admin_or_owner),
) -> ApiResponse[UserOut]:
    result = services.update_user(user_id, payload, current["namespace_id"])
    return ApiResponse(message="User updated.", data=result)
