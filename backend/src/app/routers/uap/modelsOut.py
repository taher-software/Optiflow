from pydantic import BaseModel, Field


class UapOut(BaseModel):
    """A UAP (Unite Autonome de Production / production area) as returned by
    the API."""

    id: str = Field(..., description="UAP id.")
    name: str = Field(..., description="UAP name.")
    description: str = Field(..., description="UAP description.")
    namespace_id: str = Field(..., description="Tenant the UAP belongs to.")
    maintenance_agent_ids: list[str] = Field(
        ..., description="Ids of users with the 'maintenance agent' role assigned to this UAP."
    )
    production_agent_ids: list[str] = Field(
        ..., description="Ids of users with the 'production agent' role assigned to this UAP."
    )
    quality_agent_ids: list[str] = Field(
        ..., description="Ids of users with the 'quality agent' role assigned to this UAP."
    )
    logistic_agent_ids: list[str] = Field(
        ..., description="Ids of users with the 'logistic agent' role assigned to this UAP."
    )
    logistic_supervisor_ids: list[str] = Field(
        ..., description="Ids of users with the 'logistic supervisor' role assigned to this UAP."
    )
    maintenance_supervisor_ids: list[str] = Field(
        ...,
        description="Ids of users with the 'maintenance supervisor' role assigned to this UAP.",
    )
    quality_supervisor_ids: list[str] = Field(
        ..., description="Ids of users with the 'quality supervisor' role assigned to this UAP."
    )
    production_supervisor_ids: list[str] = Field(
        ...,
        description="Ids of users with the 'production supervisor' role assigned to this UAP.",
    )
