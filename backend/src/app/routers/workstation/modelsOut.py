from typing import Optional

from pydantic import BaseModel, Field

from src.app.globals.enum import WorkstationType


class WorkstationOut(BaseModel):
    """A workstation as returned by the API."""

    id: str = Field(..., description="Workstation id.")
    name: str = Field(..., description="Workstation name.")
    description: str = Field(..., description="Workstation description.")
    production_line_id: Optional[str] = Field(
        ..., description="Id of the production line this workstation belongs to, or `None` if independent."
    )
    type: WorkstationType = Field(..., description="Workstation classification.")
    namespace_id: str = Field(..., description="Tenant the workstation belongs to.")
    archived: bool = Field(
        default=False,
        description=(
            "Whether this workstation has been archived. Derived from "
            "`archived_at` (never stored as its own field); an archived "
            "workstation never appears here anyway, since archived "
            "resources are excluded from every list/read — this field only "
            "matters on the archive endpoint's own response."
        ),
    )


class WorkstationArchiveOut(WorkstationOut):
    """Response shape for `DELETE /workstations/{station_id}` (archiving).
    A workstation archive never cascades (it has no children), so both id
    lists are always empty — kept for a consistent response shape across the
    three archive endpoints."""

    archived_production_line_ids: list[str] = Field(default_factory=list)
    archived_workstation_ids: list[str] = Field(default_factory=list)
