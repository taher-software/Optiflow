from fastapi import APIRouter, Depends, status

from src.app.core.api_response import ApiResponse
from src.app.core.deps import require_roles
from src.app.globals.enum import Role

from src.app.routers.production_line import services
from src.app.routers.production_line.modelsIn import (
    CreateProductionLineIn,
    UpdateProductionLineIn,
)
from src.app.routers.production_line.modelsOut import ProductionLineOut

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
        "whitespace and case). `uap_id` must reference an existing UAP "
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
        "Partially updates a production line in the caller's namespace. If "
        "`name` is provided it must be unique within the namespace "
        "(comparison ignores leading/trailing whitespace and case; the line "
        "being updated is excluded from the comparison, so keeping the same "
        "name, even with a different case, never conflicts). Any field "
        "omitted (`None`) is left untouched. If `uap_id` is provided it is "
        "re-validated against the caller's namespace. Restricted to owner/"
        "admin/production supervisor."
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
    response_model=ApiResponse[ProductionLineOut],
    summary="Delete a production line",
    description=(
        "Deletes a production line from the caller's namespace and returns "
        "the deleted record. Restricted to owner/admin/production supervisor."
    ),
    responses={
        404: {"description": "Production line not found in the caller's namespace."}
    },
)
async def delete_production_line(
    line_id: str,
    current: dict = Depends(_production_line_scope),
) -> ApiResponse[ProductionLineOut]:
    result = services.delete_production_line(line_id, current["namespace_id"])
    return ApiResponse(message="Production line deleted.", data=result)
