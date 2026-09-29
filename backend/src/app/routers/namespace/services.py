"""Business logic for the `namespace` router.

Today this router has a single endpoint: `DELETE /namespaces/{namespace_id}`,
a back-office tenant-wipe. It deletes every piece of Firestore data a
namespace owns, per the BOM's inventory
(`.claude/specs/namespace-cleanup.md`), and nothing else — `plan` (global)
and `temporary_connection` (keyed by device, no namespace id) are never
touched.

Deletion order, deliberately fixed so a partial failure (mid-cleanup crash,
Firestore error) can be retried and still mean something:
  1. `Users` / `uap` / `production_line` / `workstation` docs scoped by
     `namespace_id`, deleted via `FirestoreClient.delete_matching_documents`
     — paged keys-only, never loading more than one page of a (possibly
     large) tenant's documents into memory at once.
  2. `down_time/{namespace_id}` and everything under it (the
     `issues` subcollection — downtime tickets) via
     `FirestoreClient.recursive_delete_document`, Firestore's own
     server-side recursive delete. Same for
     `NamespaceSettings/{namespace_id}` and its `settings` subcollection.
     Both are counted first via `FirestoreClient.count_subdocuments` (a
     `count()` aggregation query — no documents loaded, just a number)
     *before* the recursive delete, since `recursive_delete`'s own return
     value is one undifferentiated total across parent + every descendant,
     not broken down per subcollection.
  3. `namespace/{namespace_id}` itself, **last**. Retrying a failed cleanup
     is safe: every step above is idempotent (re-deleting an already-gone
     doc, or recursively deleting an empty/absent subtree, is a no-op), and
     as long as the `namespace` doc itself is still there, this endpoint's
     own 404 check still resolves — a caller can safely re-run `DELETE`
     until it succeeds.
  4. A final sweep of `down_time/{namespace_id}` *after* the namespace doc
     is gone: `add_down_time` runs asynchronously (see
     `src.app.async_jobs.add_down_time`), so a ticket-creation request that
     was in flight when this cleanup started could still write a fresh
     `down_time/{namespace_id}/issues/*` doc after step 2's recursive
     delete already ran. This sweep counts and removes any such doc, adding
     it to the `issues` count, so the endpoint doesn't silently leave an
     orphaned ticket behind for a namespace whose `namespace_id` no longer
     exists.

The response's per-collection counts (`NamespaceCleanupDeletedCounts`) name
exactly what they count: `issues` is the number of
`down_time/{namespace_id}/issues/*` docs deleted (steps 2 + 4 combined), and
`settings` is the number of `NamespaceSettings/{namespace_id}/settings/*`
docs deleted (step 2) — in both cases the parent doc
(`down_time/{namespace_id}` / `NamespaceSettings/{namespace_id}`) is still
deleted as part of the same step, it is just not folded into that count.
"""

import logging

from fastapi import HTTPException, status

from src.app.core.firestore import (
    NAMESPACE_COLLECTION,
    NAMESPACE_SETTINGS_COLLECTION,
    PRODUCTION_LINE_COLLECTION,
    SETTINGS_SUBCOLLECTION,
    UAP_COLLECTION,
    USERS_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.gcp import get_firestore_client

from src.app.routers.namespace.modelsOut import (
    NamespaceCleanupDeletedCounts,
    NamespaceCleanupOut,
)

logger = logging.getLogger(__name__)

# Mirrors `src.app.routers.down_time.services.DOWN_TIME_COLLECTION` /
# `ISSUES_SUBCOLLECTION` — downtime tickets live at
# `down_time/{namespace_id}/issues/{issue_id}`.
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"


def _delete_subtree_counted(client, collection_name: str, parent_id: str, sub_collection: str) -> int:
    """Count `collection_name/parent_id/sub_collection`, recursively delete
    `collection_name/parent_id` (parent doc + that subcollection), and
    return the pre-deletion count. See the module docstring for why the
    count is taken first rather than derived from `recursive_delete`'s own
    return value."""
    count = client.count_subdocuments(collection_name, parent_id, sub_collection)
    client.recursive_delete_document(collection_name, parent_id)
    return count


def delete_namespace(namespace_id: str) -> NamespaceCleanupOut:
    """Wipe a namespace and every piece of data it owns. Irreversible.

    Raises `HTTPException(404)` when `namespace/{namespace_id}` doesn't
    exist. No confirmation field, no subscription-state check (A3) — see
    the BOM for the bucket-A decisions this implements.
    """
    client = get_firestore_client()

    namespace = client.get_document(NAMESPACE_COLLECTION, namespace_id)
    if not namespace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Namespace not found."
        )

    logger.warning(f"namespace cleanup started: namespace_id={namespace_id}")

    users_deleted = client.delete_matching_documents(
        USERS_COLLECTION, {"namespace_id": namespace_id}
    )
    uaps_deleted = client.delete_matching_documents(
        UAP_COLLECTION, {"namespace_id": namespace_id}
    )
    lines_deleted = client.delete_matching_documents(
        PRODUCTION_LINE_COLLECTION, {"namespace_id": namespace_id}
    )
    workstations_deleted = client.delete_matching_documents(
        WORKSTATION_COLLECTION, {"namespace_id": namespace_id}
    )

    issues_deleted = _delete_subtree_counted(
        client, DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION
    )
    settings_deleted = _delete_subtree_counted(
        client, NAMESPACE_SETTINGS_COLLECTION, namespace_id, SETTINGS_SUBCOLLECTION
    )

    # Namespace doc deleted last — see module docstring.
    namespace_deleted = int(client.delete_document(NAMESPACE_COLLECTION, namespace_id))

    # Final sweep: catch a ticket written by an `add_down_time` job that was
    # still in flight when the recursive delete above already ran (see
    # module docstring, step 4).
    extra_issues = client.count_subdocuments(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION
    )
    if extra_issues:
        client.recursive_delete_document(DOWN_TIME_COLLECTION, namespace_id)
        issues_deleted += extra_issues

    counts = {
        "users": users_deleted,
        "uaps": uaps_deleted,
        "production_lines": lines_deleted,
        "workstations": workstations_deleted,
        "issues": issues_deleted,
        "settings": settings_deleted,
        "namespace": namespace_deleted,
    }
    logger.warning(
        f"namespace cleanup completed: namespace_id={namespace_id} deleted={counts}"
    )

    return NamespaceCleanupOut(
        namespace_id=namespace_id,
        deleted=NamespaceCleanupDeletedCounts(**counts),
    )
