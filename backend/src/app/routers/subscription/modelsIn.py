from pydantic import BaseModel, Field, field_validator

from src.app.core.naming import reject_blank_name


class CreateSubscriptionIn(BaseModel):
    """Payload to subscribe a namespace to a plan.

    Which subscription (base vs extra/quota) is touched is decided by the
    matched plan's `quota` (`null` => base, non-null => extra) — see
    `POST /subscriptions`.
    """

    namespace_id: str = Field(
        ...,
        min_length=1,
        description="Id of the namespace (tenant) being subscribed.",
        examples=["8f3a1c9e-1111-4a2b-9c3d-4e5f6a7b8c9d"],
    )
    plan_name: str = Field(
        ...,
        min_length=1,
        description=(
            "Name of an existing plan (matched the same way as `Plan.name` "
            "uniqueness: stripped and lowercased)."
        ),
        examples=["Pro"],
    )
    today_start_day: bool = Field(
        default=False,
        description=(
            "When `true`, the new period always starts today, even if the "
            "current period (of the same kind, base or extra) hasn't ended "
            "yet. When `false` (default), the new period starts the day "
            "after the current one ends, unless there is no current end "
            "date, in which case it also starts today."
        ),
    )

    @field_validator("namespace_id", "plan_name")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        return reject_blank_name(value)
