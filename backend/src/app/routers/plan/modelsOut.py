from typing import Optional

from pydantic import BaseModel, Field


class PlanOut(BaseModel):
    """A commercial plan as returned by the API."""

    id: str = Field(..., description="Plan id.", examples=["plan_5b2f1d"])
    name: str = Field(..., description="Plan name.", examples=["Pro"])
    price: float = Field(
        ..., description="Plan price, a plain number (no currency).", examples=[49.9]
    )
    duration: int = Field(
        ..., description="Subscription duration in days.", examples=[30]
    )
    quota: Optional[int] = Field(
        default=None,
        description=(
            "Quota granted by this plan, or `None` for a base plan (see "
            "`POST /subscriptions`)."
        ),
        examples=[500],
    )
    maintenance_price: Optional[float] = Field(
        default=None,
        description="Maintenance price (no currency), or `None` when not set.",
        examples=[9.9],
    )
