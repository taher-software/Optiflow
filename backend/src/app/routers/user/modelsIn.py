from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator

from src.app.globals.enum import EMAIL_REQUIRED_ROLES, Role


class CreateUserIn(BaseModel):
    """Payload to create a new user within the caller's namespace."""

    first_name: str = Field(
        ..., min_length=1, description="User first name.", examples=["Alex"]
    )
    last_name: str = Field(
        ..., min_length=1, description="User last name.", examples=["Martin"]
    )
    role: Role = Field(
        ...,
        description="Role to assign (owner is not assignable).",
        examples=["supervisor"],
    )
    email: Optional[EmailStr] = Field(
        default=None,
        description="Required for admin, manager, and supervisor roles.",
        examples=["alex.martin@example.com"],
    )
    password: Optional[str] = Field(
        default=None,
        min_length=6,
        description=(
            "Initial password. Required when `email` is set (including "
            "implicitly, for admin/manager/supervisor roles); optional "
            "otherwise. A user created without a password (and without an "
            "email) signs in from mobile with a security code via `POST "
            "/auth/check-user-code`, never with `POST /auth/login`."
        ),
        examples=["s3cret-init"],
    )

    @model_validator(mode="after")
    def _validate(self) -> "CreateUserIn":
        if self.role is Role.OWNER:
            raise ValueError("The owner role cannot be assigned.")
        if self.role in EMAIL_REQUIRED_ROLES and not self.email:
            raise ValueError(
                "Email is required for admin, manager, and supervisor roles."
            )
        if self.email and not self.password:
            raise ValueError("Password is required when an email is set.")
        return self


class SetOnlineIn(BaseModel):
    """Payload for a user to declare themselves online/offline for team push
    notifications. `online` is required (no default) so an empty body cannot
    silently change the caller's state."""

    online: bool = Field(
        ...,
        strict=True,
        description=(
            "Explicit reachability state to set on the caller's own account: "
            "`True` to receive team push notifications, `False` to opt out of "
            "them. Supervisor escalations are still delivered regardless of "
            "this value. Strictly typed: string/int look-alikes (\"yes\", 1, "
            "\"true\") are rejected rather than silently coerced."
        ),
        examples=[False],
    )


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
