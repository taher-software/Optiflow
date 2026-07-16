from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserOut(BaseModel):
    """A user as returned by the API (never includes the password hash)."""

    id: str = Field(..., description="User id.")
    first_name: str = Field(..., description="User first name.")
    last_name: str = Field(..., description="User last name.")
    role: str = Field(..., description="User role.")
    email: Optional[EmailStr] = Field(default=None, description="User email, if any.")
    security_code: str = Field(..., description="Unique 4-digit security code.")
    namespace_id: str = Field(..., description="Tenant the user belongs to.")
