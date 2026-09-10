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
    archived: bool = Field(
        default=False,
        description=(
            "Whether this production line has been archived. Derived from "
            "`archived_at` (never stored as its own field); an archived "
            "line never appears here anyway, since archived resources are "
            "excluded from every list/read — this field only matters on the "
            "archive endpoint's own response."
        ),
    )


class ProductionLineArchiveOut(ProductionLineOut):
    """Response shape for `DELETE /production-lines/{line_id}` (archiving):
    the archived line itself, plus every workstation swept into the cascade.
    """

    archived_production_line_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Always empty: a production line's archive does not cascade to "
            "other production lines. Kept for a consistent response shape "
            "across the three archive endpoints."
        ),
    )
    archived_workstation_ids: list[str] = Field(
        default_factory=list,
        description="Ids of every workstation archived by this cascade.",
    )
