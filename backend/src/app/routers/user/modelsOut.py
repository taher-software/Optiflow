from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserOut(BaseModel):
    """A user as returned by the API (never includes the password hash)."""

    id: str = Field(..., description="User id.", examples=["u_7f3a9c"])
    first_name: str = Field(..., description="User first name.", examples=["Alex"])
    last_name: str = Field(..., description="User last name.", examples=["Martin"])
    role: str = Field(..., description="User role.", examples=["supervisor"])
    email: Optional[EmailStr] = Field(
        default=None,
        description="User email, if any.",
        examples=["alex.martin@example.com"],
    )
    security_code: str = Field(
        ..., description="Unique 4-digit security code.", examples=["4821"]
    )
    namespace_id: str = Field(
        ..., description="Tenant the user belongs to.", examples=["plant-lyon-01"]
    )
    online: bool = Field(
        default=True,
        description=(
            "Whether the user is reachable for team push notifications. A user "
            "document with no `online` key is considered online (defaults to "
            "`True`) — this mirrors the notification filters' own "
            "`u.get(\"online\", True)` rule. Going offline suppresses team "
            "notifications only: supervisor escalations ignore this flag and "
            "are always delivered, even to an offline user."
        ),
        examples=[True],
    )
