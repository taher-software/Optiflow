"""Shared shift clock-window helpers.

Used by the KPI service's planned-time computation
(`src.app.routers.kpi.services`). Midnight-wrap aware: `end_time` earlier
than `start_time` means the shift crosses midnight (e.g. 22:00 -> 06:00).
"""


def parse_hhmm(value: str) -> int:
    """`"HH:MM"` -> minutes since midnight.

    Raises:
        ValueError: `value` isn't two `:`-separated integers.
    """
    hours_str, sep, minutes_str = value.partition(":")
    if not sep:
        raise ValueError(f"not a HH:MM time: {value!r}")
    return int(hours_str) * 60 + int(minutes_str)


def window_length_minutes(start_minutes: int, end_minutes: int) -> int:
    """Length, in minutes, of the clock window `[start_minutes, end_minutes)`
    (both already minutes-since-midnight). Midnight-wrap aware: `end_minutes
    <= start_minutes` means the window crosses midnight (e.g. 22:00 ->
    06:00). Callers must exclude the zero-length case themselves (start ==
    end is ambiguous between "0 minutes" and "24h")."""
    return (
        (end_minutes - start_minutes)
        if end_minutes > start_minutes
        else (24 * 60 - start_minutes) + end_minutes
    )


def break_minutes_in_window(
    shift_start: str, shift_end: str, break_start: str, break_end: str
) -> int:
    """Validate that the break window `break_start` -> `break_end` (`"HH:MM"`)
    is of non-zero length and falls strictly **inside** the shift window
    `shift_start` -> `shift_end` (bounds included), both midnight-wrap aware
    the same way (a 22:00 -> 06:00 shift may have a 01:00 -> 01:30 break).
    Returns the break's length in minutes.

    Shared by the settings input model (`routers/settings/modelsIn.py`) and
    the KPI planned-time computation (`routers/kpi/services.py`) so the two
    never diverge on what counts as a valid/contained break (revision 2
    already lost time to that kind of split logic for `break_minutes`).

    Raises:
        ValueError: the break is zero-length, not contained in the shift
            window, or as long as (or longer than) the shift window itself.
    """
    if break_start == break_end:
        raise ValueError("break_start_time and break_end_time must differ")

    shift_start_min = parse_hhmm(shift_start)
    shift_end_min = parse_hhmm(shift_end)
    break_start_min = parse_hhmm(break_start)
    break_end_min = parse_hhmm(break_end)

    window_len = window_length_minutes(shift_start_min, shift_end_min)
    break_len = window_length_minutes(break_start_min, break_end_min)

    if break_len >= window_len:
        raise ValueError("break window must be strictly shorter than the shift window")

    # Offset of the break's start from the shift's start, wrap-aware (always
    # in [0, 1440)); the break is contained iff it starts at/after the shift
    # start and ends at/before the shift end, walking forward from there.
    break_start_offset = (break_start_min - shift_start_min) % (24 * 60)
    break_end_offset = break_start_offset + break_len
    if break_start_offset < 0 or break_end_offset > window_len:
        raise ValueError("break window must fall within the shift window")

    return break_len
