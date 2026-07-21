from typing import Optional

from pydantic import BaseModel, Field, model_validator

from src.app.globals.enum import DownTimeType, Process, ProductionScope

# `department` may only ever be one of these two processes when it's supplied
# (a Setup/Changeover can be routed to production or maintenance — never
# quality/logistic).
_ALLOWED_SETUP_CHANGEOVER_DEPARTMENTS = {Process.PRODUCTION, Process.MAINTENANCE}


class CreateDownTimeIn(BaseModel):
    """Payload to report a new downtime (production agent only).

    `production_scope` selects the granularity the downtime is declared at
    (plant / UAP / production line / work station); the matching id field is
    then required (see the field validation rules below). `department` is
    required, and restricted to production/maintenance, only when
    `down_time_type` is Setup / Changeover — for every other type it must be
    omitted, since the owning process is derived automatically from the type.
    """

    production_scope: ProductionScope = Field(
        ..., description="Granularity level the downtime is declared at."
    )
    uap_id: Optional[str] = Field(
        default=None,
        min_length=1,
        description=(
            "Id of the UAP (production area) the downtime applies to. "
            "Required when `production_scope` is `uap`."
        ),
    )
    production_line_id: Optional[str] = Field(
        default=None,
        min_length=1,
        description=(
            "Id of the production line the downtime applies to. Required "
            "when `production_scope` is `production line`."
        ),
    )
    workstation_id: Optional[str] = Field(
        default=None,
        min_length=1,
        description=(
            "Id of the workstation the downtime applies to. Required when "
            "`production_scope` is `work station`."
        ),
    )
    down_time_type: DownTimeType = Field(
        ..., description="Root cause category of the downtime."
    )
    department: Optional[Process] = Field(
        default=None,
        description=(
            "Process/department the ticket is routed to. Required (and "
            "restricted to `production`/`maintenance`) only when "
            "`down_time_type` is Setup / Changeover; must be omitted "
            "otherwise."
        ),
    )

    @model_validator(mode="after")
    def _validate_department(self) -> "CreateDownTimeIn":
        if self.down_time_type == DownTimeType.SETUP_CHANGEOVER:
            if self.department is None:
                raise ValueError(
                    "department is required when down_time_type is "
                    "Setup / Changeover."
                )
            if self.department not in _ALLOWED_SETUP_CHANGEOVER_DEPARTMENTS:
                raise ValueError(
                    "department must be 'production' or 'maintenance' when "
                    "down_time_type is Setup / Changeover."
                )
        elif self.department is not None:
            raise ValueError(
                "department must be omitted unless down_time_type is "
                "Setup / Changeover."
            )
        return self

    @model_validator(mode="after")
    def _validate_scope_id(self) -> "CreateDownTimeIn":
        if self.production_scope == ProductionScope.UAP and not self.uap_id:
            raise ValueError("uap_id is required when production_scope is 'uap'.")
        if (
            self.production_scope == ProductionScope.PRODUCTION_LINE
            and not self.production_line_id
        ):
            raise ValueError(
                "production_line_id is required when production_scope is "
                "'production line'."
            )
        if (
            self.production_scope == ProductionScope.WORK_STATION
            and not self.workstation_id
        ):
            raise ValueError(
                "workstation_id is required when production_scope is "
                "'work station'."
            )
        return self
