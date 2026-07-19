from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class AuthUserOut(BaseModel):
    """The authenticated user returned on login."""

    id: str = Field(..., description="User id.")
    email: Optional[EmailStr] = Field(
        default=None, description="User email / username, if any."
    )
    first_name: str = Field(..., description="User first name.")
    last_name: str = Field(..., description="User last name.")
    role: str = Field(..., description="User role.")
    namespace_id: str = Field(..., description="Tenant (namespace) the user belongs to.")
    avatar_url: Optional[str] = Field(default=None, description="Optional avatar URL.")


class LoginOut(BaseModel):
    """Result of a successful login."""

    access_token: str = Field(..., description="Bearer token for authenticated requests.")
    token_type: str = Field(default="bearer", description="Token type.")
    user: AuthUserOut = Field(..., description="The authenticated user.")
