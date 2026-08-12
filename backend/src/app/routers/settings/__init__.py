from fastapi import APIRouter, Depends, status

from src.app.core.api_response import ApiResponse
from src.app.core.deps import require_roles
from src.app.globals.enum import Role

from src.app.routers.settings import services
from src.app.routers.settings.modelsIn import (
    CreateNamespaceSettingsIn,
    UpdateNamespaceSettingsIn,
)
from src.app.routers.settings.modelsOut import NamespaceSettingsOut

router = APIRouter(prefix="/settings", tags=["settings"])

# Plant settings are managed by supervisors and above.
_settings_scope = require_roles(
    Role.OWNER, Role.ADMIN, Role.MANAGER, Role.PRODUCTION_SUPERVISOR
)


@router.post(
    "",
    response_model=ApiResponse[NamespaceSettingsOut],
    status_code=status.HTTP_201_CREATED,
    summary="Create the namespace plant settings",
    description=(
        "Creates the plant settings (shift schedule + escalation delay) for "
        "the caller's namespace. Stores a document reflecting the payload "
        "exactly. When `shift_number` > 1, the first `shift_number` shift "
        "windows are required. Restricted to owner/admin/manager/production "
        "supervisor."
    ),
    responses={
        403: {"description": "Caller lacks the required role."},
        422: {"description": "Missing shift window(s) for the declared shift count."},
    },
)
async def create_settings(
    payload: CreateNamespaceSettingsIn,
    current: dict = Depends(_settings_scope),
) -> ApiResponse[NamespaceSettingsOut]:
    result = services.create_namespace_settings(payload, current["namespace_id"])
    return ApiResponse(message="Settings created.", data=result)


@router.patch(
    "",
    response_model=ApiResponse[NamespaceSettingsOut],
    summary="Update the namespace plant settings",
    description=(
        "Partially updates the caller's namespace settings. A field omitted "
        "from the request body is left untouched. Restricted to owner/admin/"
        "manager/production supervisor."
    ),
    responses={
        403: {"description": "Caller lacks the required role."},
        404: {"description": "The namespace has no settings yet."},
    },
)
async def update_settings(
    payload: UpdateNamespaceSettingsIn,
    current: dict = Depends(_settings_scope),
) -> ApiResponse[NamespaceSettingsOut]:
    result = services.update_namespace_settings(payload, current["namespace_id"])
    return ApiResponse(message="Settings updated.", data=result)


@router.get(
    "/{namespace_id}",
    response_model=ApiResponse[NamespaceSettingsOut],
    summary="Get the namespace plant settings",
    description=(
        "Retrieves the plant settings of `namespace_id`. Tenant-scoped: a "
        "caller may only read the settings of their own namespace. Restricted "
        "to owner/admin/manager/production supervisor."
    ),
    responses={
        403: {"description": "Caller requested another namespace's settings, or lacks the role."},
        404: {"description": "The namespace has no settings yet."},
    },
)
async def get_settings(
    namespace_id: str,
    current: dict = Depends(_settings_scope),
) -> ApiResponse[NamespaceSettingsOut]:
    result = services.get_namespace_settings(namespace_id, current["namespace_id"])
    return ApiResponse(data=result)
