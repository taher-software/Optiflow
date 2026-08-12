from typing import Optional

from pydantic import BaseModel, Field

from src.app.routers.settings.modelsIn import ShiftTime


class NamespaceSettingsOut(BaseModel):
    """The plant settings of a namespace as returned by the API."""

    namespace_id: str = Field(..., description="Tenant the settings belong to.")
    shift_number: int = Field(..., description="Number of shifts the plant runs per day.")
    shift_1: Optional[ShiftTime] = Field(..., description="Clock window of shift 1, or `null`.")
    shift_2: Optional[ShiftTime] = Field(..., description="Clock window of shift 2, or `null`.")
    shift_3: Optional[ShiftTime] = Field(..., description="Clock window of shift 3, or `null`.")
    time_to_escalate: int = Field(
        ..., description="Seconds before an unresolved downtime escalates to management."
    )
