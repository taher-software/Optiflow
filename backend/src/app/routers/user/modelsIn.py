from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator

from src.app.globals.enum import EMAIL_REQUIRED_ROLES, Role


class CreateUserIn(BaseModel):
    """Payload to create a new user within the caller's namespace."""

    first_name: str = Field(..., min_length=1, description="User first name.")
    last_name: str = Field(..., min_length=1, description="User last name.")
    role: Role = Field(..., description="Role to assign (owner is not assignable).")
    email: Optional[EmailStr] = Field(
        default=None,
        description="Required for admin, manager, and supervisor roles.",
    )
    password: str = Field(..., min_length=6, description="Initial password.")

    @model_validator(mode="after")
    def _validate(self) -> "CreateUserIn":
        if self.role is Role.OWNER:
            raise ValueError("The owner role cannot be assigned.")
        if self.role in EMAIL_REQUIRED_ROLES and not self.email:
            raise ValueError(
                "Email is required for admin, manager, and supervisor roles."
            )
        return self


class UpdateUserIn(BaseModel):
    """Payload to update an existing user. All fields optional."""

    first_name: Optional[str] = Field(default=None, min_length=1)
    last_name: Optional[str] = Field(default=None, min_length=1)
    role: Optional[Role] = Field(default=None)
    email: Optional[EmailStr] = Field(default=None)
    password: Optional[str] = Field(default=None, min_length=6)

    @model_validator(mode="after")
    def _validate(self) -> "UpdateUserIn":
        if self.role is Role.OWNER:
            raise ValueError("The owner role cannot be assigned.")
        return self
