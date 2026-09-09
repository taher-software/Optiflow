from typing import Optional

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    """Credentials to log in."""

    username: str = Field(..., min_length=1, description="Username (the account email).")
    password: str = Field(..., min_length=1, description="Account password.")


class MobileLoginIn(BaseModel):
    """Log in a mobile device that is already paired with a user account."""

    device_id: str = Field(
        ..., min_length=1, description="Unique identifier of the mobile device."
    )
    push_token: Optional[str] = Field(
        default=None,
        min_length=1,
        description=(
            "Push notification token for the device. If provided and different "
            "from the stored one, it replaces it."
        ),
    )


class CheckUserCodeIn(BaseModel):
    """Pair a mobile device with a user account via their security code."""

    security_code: str = Field(
        ...,
        min_length=4,
        max_length=4,
        description=(
            "The user's current 4-character security code (unambiguous "
            "base32 alphabet: digits and uppercase letters excluding "
            "I, L, O, U). Case-insensitive -- normalised to uppercase "
            "before lookup."
        ),
    )
    device_id: str = Field(
        ..., min_length=1, description="Unique identifier of the mobile device to pair."
    )
    push_token: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Push notification token for the device, if available.",
    )
