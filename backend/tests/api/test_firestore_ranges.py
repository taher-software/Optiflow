"""Unit tests for `FirestoreClient.find_subdocuments`'s range-filter support
(prep plumbing for the upcoming KPI endpoints — see `.claude/specs/kpi-dashboard.md`
§4/§5bis.3). Exercises the equality-only fast path (unchanged), the new
`(operator, value)` list form for range queries, and operator validation.
Uses the `fake_db` fixture's in-memory `FakeFirestore` — no real Firestore.
"""

import pytest

from src.app.gcp.firestore import FirestoreClient

PARENT_COLLECTION = "down_time"
SUB_COLLECTION = "issues"


def _seed_issues(client: FirestoreClient, namespace_id: str) -> None:
    issues = [
        {"id": "i1", "created_at": "2026-06-30T23:59:59", "status": "resolved"},
        {"id": "i2", "created_at": "2026-07-01T00:00:00", "status": "resolved"},
        {"id": "i3", "created_at": "2026-07-15T12:00:00", "status": "ongoing"},
        {"id": "i4", "created_at": "2026-07-31T23:59:59", "status": "resolved"},
        {"id": "i5", "created_at": "2026-08-01T00:00:00", "status": "resolved"},
    ]
    for issue in issues:
        client.create_subdocument(
            PARENT_COLLECTION,
            namespace_id,
            SUB_COLLECTION,
            issue,
            document_id=issue["id"],
        )


class TestFindSubdocumentsRanges:
    def test_equality_still_works(self, fake_db):
        client = FirestoreClient(client=fake_db)
        _seed_issues(client, "ns-1")

        results = client.find_subdocuments(
            PARENT_COLLECTION, "ns-1", SUB_COLLECTION, {"status": "ongoing"}
        )
        assert {doc["id"] for doc in results} == {"i3"}

    def test_created_at_range_returns_only_docs_inside_the_range(self, fake_db):
        client = FirestoreClient(client=fake_db)
        _seed_issues(client, "ns-1")

        results = client.find_subdocuments(
            PARENT_COLLECTION,
            "ns-1",
            SUB_COLLECTION,
            {
                "created_at": [
                    (">=", "2026-07-01"),
                    ("<=", "2026-07-31T23:59:59"),
                ]
            },
        )
        assert {doc["id"] for doc in results} == {"i2", "i3", "i4"}

    def test_range_combined_with_equality_param(self, fake_db):
        client = FirestoreClient(client=fake_db)
        _seed_issues(client, "ns-1")

        results = client.find_subdocuments(
            PARENT_COLLECTION,
            "ns-1",
            SUB_COLLECTION,
            {
                "created_at": [
                    (">=", "2026-07-01"),
                    ("<=", "2026-07-31T23:59:59"),
                ],
                "status": "resolved",
            },
        )
        assert {doc["id"] for doc in results} == {"i2", "i4"}

    def test_invalid_operator_raises_value_error(self, fake_db):
        client = FirestoreClient(client=fake_db)
        _seed_issues(client, "ns-1")

        with pytest.raises(ValueError):
            client.find_subdocuments(
                PARENT_COLLECTION,
                "ns-1",
                SUB_COLLECTION,
                {"created_at": [("~=", "2026-07-01")]},
            )

    def test_raw_list_equality_value_raises_value_error(self, fake_db):
        """Fix #8 — a raw list passed as a plain equality value (not a list
        of `(operator, value)` pairs) must be rejected outright rather than
        silently misinterpreted as pair-iteration (which would previously
        have unpacked each list *element* as if it were an `(operator,
        value)` pair)."""
        client = FirestoreClient(client=fake_db)
        _seed_issues(client, "ns-1")

        with pytest.raises(ValueError, match=r"params\[tags\] must be a list of"):
            client.find_subdocuments(
                PARENT_COLLECTION, "ns-1", SUB_COLLECTION, {"tags": ["a", "b"]}
            )

    def test_malformed_pair_raises_before_building_query(self, fake_db):
        """A list containing something that isn't a 2-item (operator, value)
        pair is also rejected, and validated for every param BEFORE any
        query is built (fix #8) — a later, valid param must not have
        already been applied."""
        client = FirestoreClient(client=fake_db)
        _seed_issues(client, "ns-1")

        with pytest.raises(ValueError, match=r"params\[created_at\] must be a list of"):
            client.find_subdocuments(
                PARENT_COLLECTION,
                "ns-1",
                SUB_COLLECTION,
                {"created_at": [(">=", "2026-07-01", "extra")], "status": "resolved"},
            )

    def test_array_equality_now_requires_explicit_operator_pair(self, fake_db):
        """The documented workaround for fix #8: explicit `[("==", [...])]`
        still works for array-valued equality."""
        client = FirestoreClient(client=fake_db)
        client.create_subdocument(
            PARENT_COLLECTION, "ns-1", SUB_COLLECTION, {"id": "i6", "tags": ["a", "b"]}, document_id="i6"
        )

        results = client.find_subdocuments(
            PARENT_COLLECTION, "ns-1", SUB_COLLECTION, {"tags": [("==", ["a", "b"])]}
        )
        assert {doc["id"] for doc in results} == {"i6"}

    def test_namespace_scoping_untouched(self, fake_db):
        client = FirestoreClient(client=fake_db)
        _seed_issues(client, "ns-1")
        _seed_issues(client, "ns-2")

        results = client.find_subdocuments(
            PARENT_COLLECTION, "ns-2", SUB_COLLECTION, {"status": "ongoing"}
        )
        assert {doc["id"] for doc in results} == {"i3"}
