from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.app.core.naming import reject_blank_name


class CreatePlanIn(BaseModel):
    """Payload to create a new commercial plan (platform/back-office)."""

    name: str = Field(
        ...,
        min_length=1,
        description=(
            "Plan name. Must be unique across every plan once stripped and "
            "lowercased; must not be blank after stripping."
        ),
        examples=["Pro"],
    )
    price: float = Field(
        ...,
        ge=0,
        description="Plan price, a plain number (no currency), must be >= 0.",
        examples=[49.9],
    )
    duration: int = Field(
        ...,
        ge=1,
        description="Subscription duration in days, must be >= 1.",
        examples=[30],
    )
    quota: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "Quota granted by this plan, when present must be >= 0. `null` "
            "(the default) means this is a base plan; a non-null quota "
            "means this is an extra (quota) plan — see `POST /subscriptions`."
        ),
        examples=[500],
    )

    @field_validator("name")
    @classmethod
    def _reject_blank_name(cls, value: str) -> str:
        return reject_blank_name(value)


class UpdatePlanIn(BaseModel):
    """Payload to update an existing plan. Every field optional.

    Partial-update semantics: only fields present in `model_fields_set` are
    applied. `quota` distinguishes "omitted" (left unchanged) from
    "explicitly set to `null`" via `model_fields_set`, not via the value
    alone, so a plan can be turned back into a base plan (quota removed).
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        description="New plan name. Omit to leave unchanged.",
        examples=["Pro"],
    )
    price: Optional[float] = Field(
        default=None,
        ge=0,
        description="New plan price, must be >= 0. Omit to leave unchanged.",
        examples=[49.9],
    )
    duration: Optional[int] = Field(
        default=None,
        ge=1,
        description="New duration in days, must be >= 1. Omit to leave unchanged.",
        examples=[30],
    )
    quota: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "New quota. Omit to leave unchanged; send explicitly as `null` "
            "to clear it (turning this back into a base plan); send a "
            "non-negative integer to set it."
        ),
        examples=[500],
    )

    @field_validator("name")
    @classmethod
    def _reject_blank_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return reject_blank_name(value)
