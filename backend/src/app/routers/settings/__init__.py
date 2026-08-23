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
        "exactly. The first `shift_number` shift windows are always "
        "required — including `shift_1` when `shift_number == 1` (revision "
        "3, §5bis.4bis). Each shift window may optionally carry a break, "
        "given as `break_start_time`/`break_end_time` (both or neither), "
        "which must fall inside the shift window. Restricted to "
        "owner/admin/manager/production supervisor."
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
        "from the request body is left untouched. The resulting document "
        "(existing settings merged with this payload) must still carry a "
        "shift window for every shift up to `shift_number` — a PATCH that "
        "would leave one missing (e.g. raising `shift_number` without "
        "supplying the new shift's window) is rejected. Restricted to "
        "owner/admin/manager/production supervisor."
    ),
    responses={
        403: {"description": "Caller lacks the required role."},
        404: {"description": "The namespace has no settings yet."},
        422: {
            "description": (
                "The merged document would be missing a required shift window."
            )
        },
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
