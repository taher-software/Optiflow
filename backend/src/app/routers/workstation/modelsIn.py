from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.app.core.naming import reject_blank_name
from src.app.globals.enum import WorkstationType


class CreateWorkstationIn(BaseModel):
    """Payload to create a new workstation within the caller's namespace."""

    name: str = Field(
        ...,
        min_length=1,
        description=(
            "Workstation name. Must be unique within the namespace once "
            "stripped and lowercased; must not be blank after stripping."
        ),
    )
    description: str = Field(default="", description="Workstation description.")
    production_line_id: Optional[str] = Field(
        default=None,
        min_length=1,
        description=(
            "Id of the production line this workstation belongs to. `None` "
            "means an independent workstation (not attached to any line)."
        ),
    )
    type: WorkstationType = Field(..., description="Workstation classification.")

    @field_validator("name")
    @classmethod
    def _reject_blank_name(cls, value: str) -> str:
        return reject_blank_name(value)


class UpdateWorkstationIn(BaseModel):
    """Payload to update an existing workstation. All fields optional.

    Partial-update semantics: only fields present in `model_fields_set` are
    applied. In particular `production_line_id` distinguishes "omitted" (left
    untouched) from "explicitly set to `null`" (detaches the workstation,
    making it independent) via `model_fields_set`, not via the value alone.
    """

    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None)
    production_line_id: Optional[str] = Field(default=None, min_length=1)
    type: Optional[WorkstationType] = Field(default=None)

    @field_validator("name")
    @classmethod
    def _reject_blank_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return reject_blank_name(value)
