from fastapi import APIRouter, Depends, status

from src.app.core.api_response import ApiResponse
from src.app.core.deps import require_roles
from src.app.globals.enum import Role

from src.app.routers.user import services
from src.app.routers.user.modelsIn import CreateUserIn, UpdateUserIn
from src.app.routers.user.modelsOut import UserOut

router = APIRouter(prefix="/users", tags=["users"])

# Only owners and admins may manage users.
_admin_or_owner = require_roles(Role.OWNER, Role.ADMIN)


@router.post(
    "",
    response_model=ApiResponse[UserOut],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description=(
        "Creates a user in the caller's namespace and allocates a unique 4-digit "
        "security code. Restricted to owner/admin. The owner role cannot be assigned; "
        "email is required for admin, manager, and supervisor roles."
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
