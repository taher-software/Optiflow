from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class CompanyIn(BaseModel):
    """Step 1 — namespace (company) information."""

    company_name: str = Field(..., min_length=1, description="Registered company name.")
    adress: str = Field(..., min_length=1, description="Company address.")
    code_postal: str = Field(..., min_length=1, description="Postal code.")
    phone_number: str = Field(..., min_length=1, description="Primary phone number.")
    tax_identification_number: str = Field(
        ..., min_length=1, description="Tax identification number."
    )
    country: str = Field(..., min_length=1, description="Country.")
    city: str = Field(..., min_length=1, description="City.")


class OwnerIn(BaseModel):
    """Step 2 — owner user information."""

    firstname: str = Field(..., min_length=1, description="Owner first name.")
    lastname: str = Field(..., min_length=1, description="Owner last name.")
    email: EmailStr = Field(..., description="Owner email (used as the username).")
    avatar_url: Optional[str] = Field(default=None, description="Optional avatar URL.")


class RegisterAccountIn(BaseModel):
    """Payload to register a new namespace and its owner user."""

    company: CompanyIn
    owner: OwnerIn


class ConfirmAccountIn(BaseModel):
    """Payload to confirm an account and finalize it."""

    token: str = Field(..., min_length=1, description="Account-confirmation token.")


class ResendConfirmationIn(BaseModel):
    """Payload to resend the account-confirmation email."""

    email: EmailStr = Field(
        ..., description="Email of the account to resend the confirmation to."
    )
