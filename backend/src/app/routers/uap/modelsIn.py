from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.app.core.naming import reject_blank_name


class CreateUapIn(BaseModel):
    """Payload to create a new UAP (Unite Autonome de Production / production
    area) within the caller's namespace."""

    name: str = Field(
        ...,
        min_length=1,
        description=(
            "UAP name. Must be unique within the namespace once stripped and "
            "lowercased; must not be blank after stripping."
        ),
    )
    description: str = Field(default="", description="UAP description.")
    maintenance_agent_ids: list[str] = Field(
        default_factory=list,
        description="Ids of users with the 'maintenance agent' role assigned to this UAP.",
    )
    production_agent_ids: list[str] = Field(
        default_factory=list,
        description="Ids of users with the 'production agent' role assigned to this UAP.",
    )
    quality_agent_ids: list[str] = Field(
        default_factory=list,
        description="Ids of users with the 'quality agent' role assigned to this UAP.",
    )
    logistic_agent_ids: list[str] = Field(
        default_factory=list,
        description="Ids of users with the 'logistic agent' role assigned to this UAP.",
    )
    logistic_supervisor_ids: list[str] = Field(
        default_factory=list,
        description="Ids of users with the 'logistic supervisor' role assigned to this UAP.",
    )
    maintenance_supervisor_ids: list[str] = Field(
        default_factory=list,
        description="Ids of users with the 'maintenance supervisor' role assigned to this UAP.",
    )
    quality_supervisor_ids: list[str] = Field(
        default_factory=list,
        description="Ids of users with the 'quality supervisor' role assigned to this UAP.",
    )
    production_supervisor_ids: list[str] = Field(
        default_factory=list,
        description="Ids of users with the 'production supervisor' role assigned to this UAP.",
    )

    @field_validator("name")
    @classmethod
    def _reject_blank_name(cls, value: str) -> str:
        return reject_blank_name(value)


class UpdateUapIn(BaseModel):
    """Payload to update an existing UAP. All fields optional. A `None` list
    means "don't touch"; a provided list (even an empty one) replaces it."""

    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None)
    maintenance_agent_ids: Optional[list[str]] = Field(default=None)
    production_agent_ids: Optional[list[str]] = Field(default=None)
    quality_agent_ids: Optional[list[str]] = Field(default=None)
    logistic_agent_ids: Optional[list[str]] = Field(default=None)
    logistic_supervisor_ids: Optional[list[str]] = Field(default=None)
    maintenance_supervisor_ids: Optional[list[str]] = Field(default=None)
    quality_supervisor_ids: Optional[list[str]] = Field(default=None)
    production_supervisor_ids: Optional[list[str]] = Field(default=None)

    @field_validator("name")
    @classmethod
    def _reject_blank_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return reject_blank_name(value)
