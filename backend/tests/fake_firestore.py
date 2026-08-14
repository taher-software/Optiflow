"""A minimal in-memory fake of the `google.cloud.firestore.Client` surface
used by this codebase (`collection().document().get/set/update/delete()` and
`collection().where(...).limit(...).get()`).

Only what the routers under test actually call is implemented — this is not
a general Firestore emulator. Kept in `tests/` (not `src/`) since it exists
purely to support tests, per the test skill's "mock all I/O" rule: no real
Firestore/network is ever touched.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional


class FakeSnapshot:
    """Mimics `google.cloud.firestore.DocumentSnapshot`."""

    def __init__(self, doc_id: str, data: Optional[dict[str, Any]]):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> Optional[dict[str, Any]]:
        return dict(self._data) if self._data is not None else None


class FakeDocumentRef:
    """Mimics `google.cloud.firestore.DocumentReference`.

    Also supports opening a subcollection off this document (mirrors real
    Firestore's `document.collection(name)`), so tests can exercise nested
    paths like `down_time/{namespace_id}/issues/{issue_id}`. Subcollections
    are stored in `root`, a dict shared with the owning `FakeFirestore`,
    keyed by the full dotted path so distinct parents never collide.
    """

    def __init__(
        self,
        store: dict[str, dict[str, Any]],
        doc_id: str,
        root: Optional[dict[str, dict[str, dict[str, Any]]]] = None,
        path: Optional[str] = None,
    ):
        self._store = store
        self.id = doc_id
        # `root` maps a full subcollection path -> its doc-id-keyed store.
        self._root = root
        self._path = path or doc_id

    def get(self) -> FakeSnapshot:
        return FakeSnapshot(self.id, self._store.get(self.id))

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        """Mimics `DocumentReference.set(data, merge=...)`: with `merge=True`,
        shallow-merges `data` into any existing document instead of replacing
        it wholesale (used by `FirestoreClient.update_document`)."""
        if merge and self.id in self._store:
            self._store[self.id].update(data)
        else:
            self._store[self.id] = dict(data)

    def update(self, data: dict[str, Any]) -> None:
        if self.id not in self._store:
            raise ValueError(f"document '{self.id}' does not exist")
        self._store[self.id].update(data)

    def delete(self) -> None:
        self._store.pop(self.id, None)

    def collection(self, name: str) -> "FakeCollection":
        """Mimics `DocumentReference.collection(name)`: opens/creates a
        subcollection nested under this document."""
        if self._root is None:
            raise NotImplementedError(
                "This FakeDocumentRef was not created with a root registry; "
                "subcollections are unavailable."
            )
        sub_path = f"{self._path}/{name}"
        sub_store = self._root.setdefault(sub_path, {})
        return FakeCollection(sub_store, root=self._root, path=sub_path)


def _matches(data: dict[str, Any], field: str, op: str, value: Any) -> bool:
    actual = data.get(field)
    if op == "==":
        return actual == value
    if op == "!=":
        return actual != value
    if op == ">=":
        return actual is not None and actual >= value
    if op == "<=":
        return actual is not None and actual <= value
    if op == ">":
        return actual is not None and actual > value
    if op == "<":
        return actual is not None and actual < value
    if op == "in":
        return actual in value
    if op == "not-in":
        return actual not in value
    raise NotImplementedError(f"FakeQuery does not support operator {op!r}")


class FakeQuery:
    """Mimics the chainable `where(...).limit(...).get()` query surface."""

    def __init__(
        self,
        docs: dict[str, dict[str, Any]],
        filters: Optional[list[tuple[str, str, Any]]] = None,
        limit: Optional[int] = None,
    ):
        self._docs = docs
        self._filters = filters or []
        self._limit = limit

    def where(self, field: str, op: str, value: Any) -> "FakeQuery":
        return FakeQuery(self._docs, [*self._filters, (field, op, value)], self._limit)

    def limit(self, count: int) -> "FakeQuery":
        return FakeQuery(self._docs, self._filters, count)

    def get(self) -> list[FakeSnapshot]:
        results = [
            FakeSnapshot(doc_id, data)
            for doc_id, data in self._docs.items()
            if all(_matches(data, field, op, value) for field, op, value in self._filters)
        ]
        if self._limit is not None:
            results = results[: self._limit]
        return results

    def stream(self) -> list[FakeSnapshot]:
        """Mimics `Query.stream()` (used by `FirestoreClient.find_document` /
        `find_documents`), an iterator over the same results as `.get()`."""
        return self.get()


class FakeCollection:
    """Mimics `google.cloud.firestore.CollectionReference`."""

    def __init__(
        self,
        store: dict[str, dict[str, Any]],
        root: Optional[dict[str, dict[str, dict[str, Any]]]] = None,
        path: Optional[str] = None,
    ):
        self._store = store
        self._root = root
        self._path = path

    def document(self, doc_id: Optional[str] = None) -> FakeDocumentRef:
        doc_id = doc_id or str(uuid.uuid4())
        doc_path = f"{self._path}/{doc_id}" if self._path else doc_id
        return FakeDocumentRef(self._store, doc_id, root=self._root, path=doc_path)

    def where(self, field: str, op: str, value: Any) -> FakeQuery:
        return FakeQuery(self._store).where(field, op, value)

    def get(self) -> list[FakeSnapshot]:
        return [FakeSnapshot(doc_id, data) for doc_id, data in self._store.items()]

    def stream(self) -> list[FakeSnapshot]:
        """Mimics `CollectionReference.stream()` (used by
        `FirestoreClient.find_documents` when no params are given)."""
        return self.get()


class FakeFirestore:
    """Mimics `google.cloud.firestore.Client`: a namespace of collections,
    each an in-memory dict keyed by document id."""

    def __init__(self):
        self._collections: dict[str, dict[str, dict[str, Any]]] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(
            self._collections.setdefault(name, {}), root=self._collections, path=name
        )

    def get_all(self, refs: list[FakeDocumentRef]) -> list[FakeSnapshot]:
        """Mimics `google.cloud.firestore.Client.get_all`: a single batched
        read for a list of `DocumentReference`s. Real Firestore does not
        guarantee the returned order matches `refs`, so callers must key
        results by `snapshot.id`, not by position."""
        return [ref.get() for ref in refs]
