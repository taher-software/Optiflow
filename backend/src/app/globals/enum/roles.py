from enum import Enum


class Role(str, Enum):
    """User roles within a namespace (tenant)."""

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    PRODUCTION_SUPERVISOR = "production supervisor"
    QUALITY_SUPERVISOR = "quality supervisor"
    MAINTENANCE_SUPERVISOR = "maintenance supervisor"
    PRODUCTION_AGENT = "production agent"
    MAINTENANCE_AGENT = "maintenance agent"
    QUALITY_AGENT = "quality agent"
    LOGISTIC_AGENT = "logistic agent"
    LOGISTIC_SUPERVISOR = "logistic supervisor"
