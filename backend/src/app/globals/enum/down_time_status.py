from enum import Enum


class DownTimeStatus(str, Enum):
    """Lifecycle status of a downtime ticket, from detection to closure."""

    PENDING = "pending"
    ONGOING = "ongoing"
    RESOLVED = "resolved"
    CLOSED = "closed"
