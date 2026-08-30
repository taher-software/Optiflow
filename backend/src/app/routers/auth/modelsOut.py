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
