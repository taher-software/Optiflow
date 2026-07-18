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
