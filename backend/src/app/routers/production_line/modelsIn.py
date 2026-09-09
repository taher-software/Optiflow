from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.app.core.naming import reject_blank_name


class CreateProductionLineIn(BaseModel):
    """Payload to create a new production line within the caller's namespace."""

    name: str = Field(
        ...,
        min_length=1,
        description=(
            "Production line name. Must be unique within the namespace once "
            "stripped and lowercased; must not be blank after stripping."
        ),
        examples=["Assembly Line 1"],
    )
    description: str = Field(
        default="",
        description="Production line description.",
        examples=["Final assembly for the B-series chassis."],
    )
    uap_id: Optional[str] = Field(
        default=None,
        min_length=1,
        description=(
            "Id of the UAP (Unite Autonome de Production / production area) "
            "this production line belongs to. Omit it (or send `null`) to "
            "create an independent production line, not attached to any "
            "UAP, mirroring the 'Independent' choice already offered for a "
            "workstation's `production_line_id`. When supplied, must be "
            "non-blank and exist in the caller's namespace."
        ),
        examples=["uap_9c1a2e"],
    )

    @field_validator("name")
    @classmethod
    def _reject_blank_name(cls, value: str) -> str:
        return reject_blank_name(value)


class UpdateProductionLineIn(BaseModel):
    """Payload to update an existing production line. All fields optional.

    Partial-update semantics: only fields present in `model_fields_set` are
    applied. In particular `uap_id` distinguishes "omitted" (left untouched)
    from "explicitly set to `null`" (detaches the production line, making it
    independent) via `model_fields_set`, not via the value alone — the same
    rule already used by `UpdateWorkstationIn.production_line_id`.
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        description="New production line name. Omit to leave unchanged.",
        examples=["Assembly Line 1"],
    )
    description: Optional[str] = Field(
        default=None,
        description="New production line description. Omit to leave unchanged.",
        examples=["Final assembly for the B-series chassis."],
    )
    uap_id: Optional[str] = Field(
        default=None,
        min_length=1,
        description=(
            "New UAP id. Omit to leave the current UAP unchanged; send "
            "`null` to detach the line and make it independent; send a "
            "non-blank id to attach/reattach it (re-validated against the "
            "caller's namespace)."
        ),
        examples=["uap_9c1a2e"],
    )

    @field_validator("name")
    @classmethod
    def _reject_blank_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return reject_blank_name(value)
