"""Shared name-uniqueness helper for namespace-scoped resources (UAP,
production line, workstation, ...).

Firestore has no case-insensitive query, and existing documents were written
without any pre-computed "normalized name" field, so the check here is done
in Python against the live documents of the namespace rather than against a
stored field. This is intentionally correct-without-migration: relying on a
stored `name_normalized` field would silently miss every document written
before that field existed.
"""

from fastapi import HTTPException, status

from src.app.gcp.firestore import FirestoreClient


def normalized_name(value: str) -> str:
    """Strip leading/trailing whitespace and lowercase, so `"  Ligne A "` and
    `"ligne a"` compare equal."""
    return value.strip().lower()


def reject_blank_name(value: str) -> str:
    """Pydantic validator body: reject a name that is empty once stripped
    (e.g. `"   "`) as a validation error (422), not a uniqueness conflict.
    `min_length=1` alone lets a whitespace-only string through, so every
    `name` field on these resources must also run this validator. Returns
    the value unchanged (stored as typed; only the *comparison* is
    normalized, not the stored value)."""
    if not value.strip():
        raise ValueError("name must not be blank.")
    return value


def assert_name_unique(
    client: FirestoreClient,
    collection_name: str,
    namespace_id: str,
    name: str,
    *,
    exclude_id: str | None = None,
    resource_label: str,
) -> None:
    """Ensure no other document of `collection_name` in `namespace_id` has the
    same normalized name.

    Scope is the namespace, per resource type: only documents of
    `collection_name` in `namespace_id` are considered, so a name reused in a
    different tenant, or by a resource of a different type (e.g. a
    workstation and a production line sharing a name) never conflicts.

    `exclude_id` excludes the resource being updated from the comparison, so
    saving a resource without changing its name (or only changing its case)
    never raises a false conflict.

    Raises HTTPException(409) with `detail` naming the resource
    (`resource_label`, e.g. "production line") on conflict.
    """
    candidate = normalized_name(name)
    existing_docs = client.find_documents(collection_name, {"namespace_id": namespace_id})
    for doc in existing_docs:
        if exclude_id is not None and doc.get("id") == exclude_id:
            continue
        if normalized_name(doc.get("name", "")) == candidate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A {resource_label} with this name already exists.",
            )
