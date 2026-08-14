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
