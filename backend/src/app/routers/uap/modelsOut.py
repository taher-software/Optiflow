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
    archived: bool = Field(
        default=False,
        description=(
            "Whether this UAP has been archived. Derived from `archived_at` "
            "(never stored as its own field). An archived UAP never appears "
            "here anyway, since archived resources are excluded from every "
            "list/read — this field only matters on the archive endpoint's "
            "own response."
        ),
    )


class UapArchiveOut(UapOut):
    """Response shape for `DELETE /uaps/{uap_id}` (archiving): the archived
    UAP itself, plus every production line and workstation swept into the
    cascade (see the router's docstring for the cascade rules)."""

    archived_production_line_ids: list[str] = Field(
        default_factory=list,
        description="Ids of every production line archived by this cascade.",
    )
    archived_workstation_ids: list[str] = Field(
        default_factory=list,
        description="Ids of every workstation archived by this cascade.",
    )
