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


# Roles for which an email is required (admin, manager, and all supervisors).
EMAIL_REQUIRED_ROLES = {
    Role.ADMIN,
    Role.MANAGER,
    Role.PRODUCTION_SUPERVISOR,
    Role.QUALITY_SUPERVISOR,
    Role.MAINTENANCE_SUPERVISOR,
    Role.LOGISTIC_SUPERVISOR,
}

# Roles an admin/owner may assign to a new user (everything except owner).
ASSIGNABLE_ROLES = [r for r in Role if r is not Role.OWNER]
