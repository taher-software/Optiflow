from enum import Enum


class DownTimeType(str, Enum):
    """Root cause category of a downtime ticket."""

    BREAKDOWN = "break down"
    QUALITY_ISSUE = "quality issue"
    ABSENTEEISM = "Absenteeism"
    WIP_SHORTAGE = "Work-in-Process (WIP) Shortage"
    MATERIAL_SHORTAGE = "Material / Component Shortage"
    SETUP_CHANGEOVER = "Setup / Changeover"
    OTHERS = "others"  # unclassified/unknown-cause stop
