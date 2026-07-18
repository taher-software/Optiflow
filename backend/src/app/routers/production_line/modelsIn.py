from typing import Optional

from pydantic import BaseModel, Field


class CreateProductionLineIn(BaseModel):
    """Payload to create a new production line within the caller's namespace."""

    name: str = Field(..., min_length=1, description="Production line name.")
    description: str = Field(default="", description="Production line description.")
    uap_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Id of the UAP (Unite Autonome de Production / production area) "
            "this production line belongs to. Must exist in the caller's namespace."
        ),
    )


class UpdateProductionLineIn(BaseModel):
    """Payload to update an existing production line. All fields optional; an
    omitted (`None`) field is left untouched."""

    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None)
    uap_id: Optional[str] = Field(default=None, min_length=1)
