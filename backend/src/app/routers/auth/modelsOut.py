from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class AuthUserOut(BaseModel):
    """The authenticated user returned on login."""

    id: str = Field(..., description="User id.", examples=["u_7f3a9c"])
    email: Optional[EmailStr] = Field(
        default=None,
        description="User email / username, if any.",
        examples=["alex.martin@example.com"],
    )
    first_name: str = Field(..., description="User first name.", examples=["Alex"])
    last_name: str = Field(..., description="User last name.", examples=["Martin"])
    role: str = Field(..., description="User role.", examples=["supervisor"])
    namespace_id: str = Field(
        ...,
        description="Tenant (namespace) the user belongs to.",
        examples=["plant-lyon-01"],
    )
    avatar_url: Optional[str] = Field(
        default=None,
        description="Optional avatar URL.",
        examples=["https://cdn.optiflow.app/avatars/u_7f3a9c.png"],
    )
    online: bool = Field(
        default=True,
        description=(
            "Whether the user is reachable for team push notifications. Mirrors "
            "the notification filters' `u.get(\"online\", True)` rule exactly: a "
            "user document with no `online` key is considered online (defaults "
            "to `True`). Going offline suppresses team notifications only — "
            "supervisor escalations ignore this flag and are always delivered, "
            "even to an offline user."
        ),
        examples=[True],
    )


class LoginOut(BaseModel):
    """Result of a successful login."""

    access_token: str = Field(..., description="Bearer token for authenticated requests.")
    token_type: str = Field(default="bearer", description="Token type.")
    user: AuthUserOut = Field(..., description="The authenticated user.")
    warning: Optional[bool] = Field(
        default=None,
        description=(
            "Whether the tenant's base subscription expired recently (1 to "
            "29 days ago). `None` when active or when there is no base "
            "subscription. Informational only -- login always succeeds."
        ),
        examples=[True],
    )
    blocked: Optional[bool] = Field(
        default=None,
        description=(
            "Whether the tenant's base subscription expired 30 or more days "
            "ago. `None` when active or when there is no base subscription. "
            "Informational only -- the backend refuses nothing based on it, "
            "web/mobile decide what to show."
        ),
        examples=[False],
    )
    plan_id: Optional[str] = Field(
        default=None,
        description=(
            "Id of the tenant's base subscription plan, returned whether the "
            "subscription is active or expired. `None` when the namespace has "
            "no base subscription."
        ),
        examples=["plan_5b2f1d"],
    )
    plan_name: Optional[str] = Field(
        default=None,
        description=(
            "Name of the tenant's base subscription plan. `None` when there "
            "is no base subscription, or when the plan document itself no "
            "longer exists."
        ),
        examples=["Pro"],
    )
