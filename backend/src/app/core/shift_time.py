"""Shared shift clock-window helpers.

Used by the KPI service's planned-time computation
(`src.app.routers.kpi.services`). Midnight-wrap aware: `end_time` earlier
than `start_time` means the shift crosses midnight (e.g. 22:00 -> 06:00).
"""


def parse_hhmm(value: str) -> int:
    """Parse an "HH:MM" string into minutes-since-midnight. Raises `ValueError`
    on anything malformed — callers treat that as "no match", never as a
    reason to fail ticket creation."""
    hours_str, minutes_str = value.split(":")
    hours, minutes = int(hours_str), int(minutes_str)
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ValueError(f"hour/minute out of range in '{value}'")
    return hours * 60 + minutes

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


def clock_window_elapsed_since_midnight(
    now: float, start: float, end: float
) -> float:
    """How much of the clock interval `[start, end)` falls within `[0, now]`
    (midnight-wrap aware: `end <= start` means the window crosses midnight,
    e.g. 22:00 -> 06:00), given `now`/`start`/`end` all expressed in the SAME
    unit, counted from midnight (minutes or seconds, caller's choice — the
    formula is unit-agnostic). In other words: how much of the window has
    the CURRENT CIVIL DAY occupied so far, by `now`.

    This is the one primitive behind the KPI service's "current day only"
    elapsed-time mode (`src.app.routers.kpi.services._elapsed_shift_seconds`,
    §5bis.4bis): it answers "how much of today's civil day has this clock
    window occupied, by `now`" for BOTH the shift's own window and its break
    window (a break is just another, smaller, clock window contained in the
    shift's).

    Non-wrapping window (`end > start`): the whole window lives on one civil
    day already, so this is the ordinary `clamp(now - start, 0, end -
    start)` — unchanged regardless of the wrap case below.

    Wrapping window (`end <= start`): today's civil day `[0, now]` can
    intersect the window in TWO disjoint pieces, which is why this sums
    them rather than picking one:
    - the tail of the instance that started YESTERDAY, `[0, end)` — however
      much of it falls before `now`, `min(now, end)`.
    - the start of TODAY's own instance, `[start, 24h)` — however much of
      it has elapsed by `now`, `max(0.0, now - start)`.
    Before `start` the second piece is 0 (nothing to add yet); at/after
    `start` both pieces are live simultaneously (this morning's tail already
    happened, tonight's instance is now running), hence the sum.

    Reference values for a 22:00 -> 06:00 shift: 05:00 -> 5h, 10:00 -> 6h,
    21:59 -> 6h, 22:00 -> 6h, 23:00 -> 7h.
    """
    if end > start:
        return max(0.0, min(now, end) - start)
    return min(now, end) + max(0.0, now - start)


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
