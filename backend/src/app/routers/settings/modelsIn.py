from typing import Optional

from pydantic import BaseModel, Field, model_validator

# 24-hour "HH:MM" clock time (e.g. "08:00", "23:30").
_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"

# Only shift_1 / shift_2 / shift_3 fields exist, so at most 3 shifts.
_MAX_SHIFTS = 3


class ShiftTime(BaseModel):
    """The clock window of a single work shift."""

    start_time: str = Field(
        ..., pattern=_TIME_PATTERN, description="Shift start, 24h `HH:MM` (e.g. `06:00`)."
    )
    end_time: str = Field(
        ..., pattern=_TIME_PATTERN, description="Shift end, 24h `HH:MM` (e.g. `14:00`)."
    )


def _shift_fields(values: "CreateNamespaceSettingsIn") -> list[Optional[ShiftTime]]:
    return [values.shift_1, values.shift_2, values.shift_3]


class CreateNamespaceSettingsIn(BaseModel):
    """Payload to create the plant settings of the caller's namespace.

    `shift_number` is how many shifts the plant runs per day (1–3). When it is
    greater than 1, the first `shift_number` shift windows (`shift_1`,
    `shift_2`, …) are required so each shift has an explicit clock window.
    """

    shift_number: int = Field(
        ..., ge=1, le=_MAX_SHIFTS, description="Number of shifts the plant runs per day (1–3)."
    )
    shift_1: Optional[ShiftTime] = Field(default=None, description="Clock window of shift 1.")
    shift_2: Optional[ShiftTime] = Field(default=None, description="Clock window of shift 2.")
    shift_3: Optional[ShiftTime] = Field(default=None, description="Clock window of shift 3.")
    time_to_escalate: int = Field(
        default=1800,
        ge=0,
        description=(
            "Seconds a downtime may stay unresolved before it escalates to "
            "management. Defaults to 1800 (30 minutes)."
        ),
    )

    @model_validator(mode="after")
    def _require_shift_windows(self) -> "CreateNamespaceSettingsIn":
        """When the plant runs more than one shift, every one of those shifts
        must carry its clock window (mirrors the UI requirement)."""
        if self.shift_number > 1:
            shifts = _shift_fields(self)
            missing = [i + 1 for i in range(self.shift_number) if shifts[i] is None]
            if missing:
                raise ValueError(
                    "shift window(s) required for shift "
                    + ", ".join(str(n) for n in missing)
                )
        return self


class UpdateNamespaceSettingsIn(BaseModel):
    """Payload to patch the plant settings. Every field optional — only the
    fields present in the request body are merged into the stored settings."""

    shift_number: Optional[int] = Field(default=None, ge=1, le=_MAX_SHIFTS)
    shift_1: Optional[ShiftTime] = Field(default=None)
    shift_2: Optional[ShiftTime] = Field(default=None)
    shift_3: Optional[ShiftTime] = Field(default=None)
    time_to_escalate: Optional[int] = Field(default=1800, ge=0)
