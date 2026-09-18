NAMESPACE_COLLECTION = "namespace"
USERS_COLLECTION = "Users"
UAP_COLLECTION = "uap"
PRODUCTION_LINE_COLLECTION = "production_line"
WORKSTATION_COLLECTION = "workstation"
# Platform-level (global, not tenant-scoped) commercial plans.
PLAN_COLLECTION = "plan"

# Failed mobile-pairing attempts per device (`/auth/check-user-code` lockout).
TEMPORARY_CONNECTION_COLLECTION = "temporary_connection"

# Per-namespace plant settings (shift schedule + escalation delay). Stored as a
# single document, keyed by the namespace id, in the `settings` subcollection of
# the namespace's `NamespaceSettings` parent doc:
#   NamespaceSettings/{namespace_id}/settings/{namespace_id}
NAMESPACE_SETTINGS_COLLECTION = "NamespaceSettings"
SETTINGS_SUBCOLLECTION = "settings"
