from typing import Optional

from pydantic import BaseModel, Field, model_validator

from src.app.core.shift_time import break_minutes_in_window

# 24-hour "HH:MM" clock time (e.g. "08:00", "23:30").
_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"

# Only shift_1 / shift_2 / shift_3 fields exist, so at most 3 shifts.
_MAX_SHIFTS = 3


class ShiftTime(BaseModel):
    """The clock window of a single work shift. `end_time` may be earlier than
    `start_time` (a shift that runs past midnight, e.g. 22:00 → 06:00), but the
    two must differ — a zero-length window is rejected.

    `break_start_time` / `break_end_time` (revision 3, §5bis.4bis — replaces
    the revision-2 `break_minutes`, itself removed) describe the shift's
    break as a clock window instead of a duration. Optional, but all-or-
    nothing: both provided, or neither. When provided, the break must be of
    non-zero length and fall strictly inside the shift window (bounds
    included, same midnight-wrap handling as the shift window itself — a
    22:00 → 06:00 shift may have a 01:00 → 01:30 break)."""

    start_time: str = Field(
        ..., pattern=_TIME_PATTERN, description="Shift start, 24h `HH:MM` (e.g. `06:00`)."
    )
    end_time: str = Field(
        ..., pattern=_TIME_PATTERN, description="Shift end, 24h `HH:MM` (e.g. `14:00`)."
    )
    break_start_time: Optional[str] = Field(
        default=None,
        pattern=_TIME_PATTERN,
        description=(
            "Break start, 24h `HH:MM` (e.g. `12:00`). Optional; must be "
            "provided together with `break_end_time` or not at all."
        ),
    )
    break_end_time: Optional[str] = Field(
        default=None,
        pattern=_TIME_PATTERN,
        description=(
            "Break end, 24h `HH:MM` (e.g. `12:30`). Optional; must be "
            "provided together with `break_start_time` or not at all."
        ),
    )

    @model_validator(mode="after")
    def _reject_zero_length(self) -> "ShiftTime":
        if self.start_time == self.end_time:
            raise ValueError("start_time and end_time must differ")
        return self

    @model_validator(mode="after")
    def _validate_break(self) -> "ShiftTime":
        has_start = self.break_start_time is not None
        has_end = self.break_end_time is not None
        if has_start != has_end:
            raise ValueError(
                "break_start_time and break_end_time must both be provided, or neither"
            )
        if has_start and has_end:
            try:
                break_minutes_in_window(
                    self.start_time, self.end_time, self.break_start_time, self.break_end_time
                )
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
        return self


def _shift_fields(values: "CreateNamespaceSettingsIn") -> list[Optional[ShiftTime]]:
    return [values.shift_1, values.shift_2, values.shift_3]


class CreateNamespaceSettingsIn(BaseModel):
    """Payload to create the plant settings of the caller's namespace.

    `shift_number` is how many shifts the plant runs per day (1–3). The
    first `shift_number` shift windows (`shift_1`, `shift_2`, …) are always
    required — including `shift_1` when `shift_number == 1` (revision 3,
    §5bis.4bis: a mono-shift plant now declares its real clock window
    instead of implicitly getting a 24h/day planned-time fallback)."""

    shift_number: int = Field(
        ..., ge=1, le=_MAX_SHIFTS, description="Number of shifts the plant runs per day (1–3)."
    )
    shift_1: Optional[ShiftTime] = Field(default=None, description="Clock window of shift 1.")
    shift_2: Optional[ShiftTime] = Field(default=None, description="Clock window of shift 2.")
    shift_3: Optional[ShiftTime] = Field(default=None, description="Clock window of shift 3.")
    time_to_escalate: int = Field(
        default=1800,
        ge=1,
        description=(
            "Seconds a downtime may stay unresolved before it escalates to "
            "management. Must be positive. Defaults to 1800 (30 minutes)."
        ),
    )

    @model_validator(mode="after")
    def _require_shift_windows(self) -> "CreateNamespaceSettingsIn":
        """Every one of the plant's `shift_number` shifts must carry its
        clock window (mirrors the UI requirement) — revision 3: this now
        also applies to `shift_number == 1` (previously only shifts beyond
        the first were required)."""
        shifts = _shift_fields(self)
        missing = [i + 1 for i in range(self.shift_number) if shifts[i] is None]
        if missing:
            raise ValueError(
                "shift window(s) required for shift " + ", ".join(str(n) for n in missing)
            )
        return self


class UpdateNamespaceSettingsIn(BaseModel):
    """Payload to patch the plant settings. Every field optional — only the
    fields present in the request body are merged into the stored settings.

    This model stays shape-optional on purpose (a PATCH may only touch
    `time_to_escalate`, say). The "every required shift window is present"
    invariant from `CreateNamespaceSettingsIn` is instead re-checked in
    `services.update_namespace_settings` against the **merged** document
    (existing stored settings + this payload) — only there is the resulting
    `shift_number` and the resulting `shift_1..shift_number` windows both
    known. See that function's docstring for the exact rule."""

    shift_number: Optional[int] = Field(default=None, ge=1, le=_MAX_SHIFTS)
    shift_1: Optional[ShiftTime] = Field(default=None)
    shift_2: Optional[ShiftTime] = Field(default=None)
    shift_3: Optional[ShiftTime] = Field(default=None)
    # No `default` here: this is a PATCH — an omitted field must stay absent
    # from `model_fields_set` so the merge in `services.py` leaves it untouched
    # (a default would make an omitted value indistinguishable from an
    # explicit 1800).
    time_to_escalate: Optional[int] = Field(default=None, ge=1)
