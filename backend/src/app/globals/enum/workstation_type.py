from enum import Enum


class WorkstationType(str, Enum):
    """Classification of a workstation by its impact on production flow."""

    STANDARD = "standard"
    BOTTLENECK = "bottleneck"
    CRITICAL = "critical"
