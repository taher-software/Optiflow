from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    """Credentials to log in."""

    username: str = Field(..., min_length=1, description="Username (the account email).")
    password: str = Field(..., min_length=1, description="Account password.")
