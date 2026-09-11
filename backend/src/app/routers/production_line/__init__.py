from fastapi import APIRouter, Depends, status

from src.app.core.api_response import ApiResponse
from src.app.core.deps import require_roles
from src.app.globals.enum import Role

from src.app.routers.production_line import services
from src.app.routers.production_line.modelsIn import (
    CreateProductionLineIn,
    UpdateProductionLineIn,
)
from src.app.routers.production_line.modelsOut import (
    ProductionLineArchiveOut,
    ProductionLineOut,
)

router = APIRouter(prefix="/production-lines", tags=["production-lines"])

# Owners, admins and production supervisors manage production lines.
_production_line_scope = require_roles(
    Role.OWNER, Role.ADMIN, Role.PRODUCTION_SUPERVISOR
)

# Read-only access (list/get) is additionally opened to production agents,
# who need it for the mobile declare-downtime cascading pickers.
_production_line_read_scope = require_roles(
    Role.OWNER, Role.ADMIN, Role.PRODUCTION_SUPERVISOR, Role.PRODUCTION_AGENT
)


@router.post(
    "",
    response_model=ApiResponse[ProductionLineOut],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new production line",
    description=(
        "Creates a production line in the caller's namespace. `name` must be "
        "unique within the namespace (comparison ignores leading/trailing "
        "whitespace and case). `uap_id` is optional: omit it (or send `null`) "
        "to create an independent production line, not attached to any UAP. "
        "When supplied, it must be non-blank and reference an existing UAP "
        "(production area) in the same namespace. Restricted to owner/admin/"
        "production supervisor."
    ),
    responses={
        403: {"description": "Caller lacks the required role."},
        409: {
            "description": (
                "A production line with this name already exists in the "
                "caller's namespace."
            )
        },
        422: {
            "description": "`uap_id` does not reference an existing UAP in this namespace."
        },
    },
)
async def create_production_line(
    payload: CreateProductionLineIn,
    current: dict = Depends(_production_line_scope),
) -> ApiResponse[ProductionLineOut]:
    result = services.create_production_line(payload, current["namespace_id"])
    return ApiResponse(message="Production line created.", data=result)


@router.get(
    "",
    response_model=ApiResponse[list[ProductionLineOut]],
    summary="List production lines",
    description=(
        "Lists all production lines in the caller's namespace. Restricted to "
        "owner/admin/production supervisor/production agent."
    ),
)
async def list_production_lines(
    current: dict = Depends(_production_line_read_scope),
) -> ApiResponse[list[ProductionLineOut]]:
    return ApiResponse(data=services.list_production_lines(current["namespace_id"]))


@router.get(
    "/{line_id}",
    response_model=ApiResponse[ProductionLineOut],
    summary="Get a production line",
    description=(
        "Fetches one production line by id. Restricted to owner/admin/"
        "production supervisor/production agent."
    ),
    responses={
        404: {"description": "Production line not found in the caller's namespace."}
    },
)
async def get_production_line(
    line_id: str,
    current: dict = Depends(_production_line_read_scope),
) -> ApiResponse[ProductionLineOut]:
    return ApiResponse(
        data=services.get_production_line(line_id, current["namespace_id"])
    )


@router.put(
    "/{line_id}",
    response_model=ApiResponse[ProductionLineOut],
    summary="Update a production line",
    description=(
        "Partially updates a production line in the caller's namespace. Any "
        "field omitted from the payload is left untouched. If `name` is "
        "provided it must be unique within the namespace (comparison ignores "
        "leading/trailing whitespace and case; the line being updated is "
        "excluded from the comparison, so keeping the same name, even with a "
        "different case, never conflicts).\n\n"
        "`uap_id` follows an omitted-vs-`null` distinction rather than the "
        "value alone: omit it to leave the current UAP unchanged, send it "
        "explicitly as `null` to detach the line and make it independent, or "
        "send a non-blank id to attach/reattach it (re-validated against the "
        "caller's namespace; a whitespace-only id is rejected). Restricted "
        "to owner/admin/production supervisor."
    ),
    responses={
        404: {"description": "Production line not found in the caller's namespace."},
        409: {
            "description": (
                "A production line with this name already exists in the "
                "caller's namespace."
            )
        },
        422: {
            "description": "`uap_id` does not reference an existing UAP in this namespace."
        },
    },
)
async def update_production_line(
    line_id: str,
    payload: UpdateProductionLineIn,
    current: dict = Depends(_production_line_scope),
) -> ApiResponse[ProductionLineOut]:
    result = services.update_production_line(
        line_id, payload, current["namespace_id"]
    )
    return ApiResponse(message="Production line updated.", data=result)


@router.delete(
    "/{line_id}",
    response_model=ApiResponse[ProductionLineArchiveOut],
    summary="Archive a production line",
    description=(
        "Archives a production line in the caller's namespace — "
        "irreversibly: there is no way to undo this. The line immediately "
        "disappears from every list and from `GET /production-lines/"
        "{line_id}` (which then behaves as not found), but its past "
        "downtime tickets are kept so they keep counting in the plant's "
        "KPIs. Archiving cascades to every workstation attached to this "
        "line (a workstation on another line, or an independent one, is "
        "left untouched). Archiving an already-archived line is a no-op "
        "that still returns 200. Restricted to owner/admin/production "
        "supervisor."
    ),
    responses={
        404: {"description": "Production line not found in the caller's namespace."}
    },
)
async def delete_production_line(
    line_id: str,
    current: dict = Depends(_production_line_scope),
) -> ApiResponse[ProductionLineArchiveOut]:
    result = services.delete_production_line(line_id, current["namespace_id"])
    return ApiResponse(message="Production line archived.", data=result)
