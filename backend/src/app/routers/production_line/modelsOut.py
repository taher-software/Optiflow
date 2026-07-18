from pydantic import BaseModel, Field


class ProductionLineOut(BaseModel):
    """A production line as returned by the API."""

    id: str = Field(..., description="Production line id.")
    name: str = Field(..., description="Production line name.")
    description: str = Field(..., description="Production line description.")
    uap_id: str = Field(
        ..., description="Id of the UAP (production area) this production line belongs to."
    )
    namespace_id: str = Field(..., description="Tenant the production line belongs to.")
