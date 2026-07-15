from pydantic import BaseModel, EmailStr, Field


class RegisterAccountOut(BaseModel):
    """Result of registering a new namespace (before email confirmation)."""

    namespace_id: str = Field(..., description="Id of the created namespace.")
    email: EmailStr = Field(..., description="Owner email the confirmation was sent to.")


class ConfirmAccountOut(BaseModel):
    """Result of confirming an account."""

    namespace_id: str = Field(..., description="Id of the confirmed namespace.")
    email: EmailStr = Field(..., description="Owner email / username.")
    role: str = Field(..., description="Role assigned to the owner user.")


class ResendConfirmationOut(BaseModel):
    """Result of a successful resend-confirmation request."""

    email: EmailStr = Field(..., description="Email the confirmation was resent to.")
