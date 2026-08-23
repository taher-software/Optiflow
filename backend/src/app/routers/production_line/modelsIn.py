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
    )
    description: str = Field(default="", description="Production line description.")
    uap_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Id of the UAP (Unite Autonome de Production / production area) "
            "this production line belongs to. Must exist in the caller's namespace."
        ),
    )

    @field_validator("name")
    @classmethod
    def _reject_blank_name(cls, value: str) -> str:
        return reject_blank_name(value)


class UpdateProductionLineIn(BaseModel):
    """Payload to update an existing production line. All fields optional; an
    omitted (`None`) field is left untouched."""

    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None)
    uap_id: Optional[str] = Field(default=None, min_length=1)

    @field_validator("name")
    @classmethod
    def _reject_blank_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return reject_blank_name(value)
