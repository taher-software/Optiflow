from typing import Optional

from pydantic import BaseModel, Field


class ProductionLineOut(BaseModel):
    """A production line as returned by the API."""

    id: str = Field(..., description="Production line id.", examples=["pl_5b2f1d"])
    name: str = Field(
        ..., description="Production line name.", examples=["Assembly Line 1"]
    )
    description: str = Field(
        ...,
        description="Production line description.",
        examples=["Final assembly for the B-series chassis."],
    )
    uap_id: Optional[str] = Field(
        default=None,
        description=(
            "Id of the UAP (production area) this production line belongs "
            "to, or `None` if the line is independent (not attached to any "
            "UAP)."
        ),
        examples=["uap_9c1a2e"],
    )
    namespace_id: str = Field(
        ...,
        description="Tenant the production line belongs to.",
        examples=["plant-lyon-01"],
    )
