from enum import Enum


class JobType(str, Enum):
    """Type of async job dispatched via Pub/Sub / Cloud Tasks."""

    ADD_DOWN_TIME = "add_down_time"
    NOTIFY_DOWN_TIME_UPDATE = "notify_down_time_update"
