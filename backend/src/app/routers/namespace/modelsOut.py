from pydantic import BaseModel, Field


class NamespaceCleanupDeletedCounts(BaseModel):
    """Per-collection count of documents deleted by a namespace cleanup."""

    users: int = Field(..., description="Users documents deleted.", examples=[12])
    uaps: int = Field(..., description="UAP documents deleted.", examples=[3])
    production_lines: int = Field(
        ..., description="Production line documents deleted.", examples=[4]
    )
    workstations: int = Field(
        ..., description="Workstation documents deleted.", examples=[20]
    )
    issues: int = Field(
        ...,
        description=(
            "Downtime ticket documents deleted from "
            "`down_time/{namespace_id}/issues/*`. Does NOT include the "
            "`down_time/{namespace_id}` parent doc — that parent is still "
            "deleted, just not counted here."
        ),
        examples=[150],
    )
    settings: int = Field(
        ...,
        description=(
            "Documents deleted from "
            "`NamespaceSettings/{namespace_id}/settings/*` (in practice 0 "
            "or 1, the single settings doc keyed by `namespace_id`). Does "
            "NOT include the `NamespaceSettings/{namespace_id}` parent doc "
            "— that parent is still deleted, just not counted here."
        ),
        examples=[1],
    )
    namespace: int = Field(
        ...,
        description="1 if the `namespace/{namespace_id}` doc was deleted (always 1 on a 200).",
        examples=[1],
    )


class NamespaceCleanupOut(BaseModel):
    """Result of wiping a namespace and every piece of data it owns."""

    namespace_id: str = Field(
        ..., description="Id of the deleted namespace.", examples=["ns_5b2f1d"]
    )
    deleted: NamespaceCleanupDeletedCounts = Field(
        ..., description="Per-collection counts of documents deleted."
    )
