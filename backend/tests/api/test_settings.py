"""API tests for the namespace plant-settings resource.

Covers `src/app/routers/settings/__init__.py` + `services.py`:
create (full doc, shift-window cross-validation, escalation default),
partial update (merge / 404 when absent), tenant-scoped get (own namespace
only), and the `require_roles(OWNER, ADMIN, MANAGER, PRODUCTION_SUPERVISOR)`
guard. No real Firestore is touched (see `tests/conftest.py::fake_db`, which
now also wires the settings services module).

`break_minutes` was removed from `ShiftTime` in KPI spec revision 2 (§5bis.3
— availability, the only consumer of a shift's break, was dropped). A
payload that still sends `break_minutes` is simply ignored by Pydantic
(extra fields are dropped by default) rather than rejected.

Revision 3 (§5bis.4bis): the shift window is now required from
`shift_number == 1` (a mono-shift plant declares real hours instead of
implicitly getting 24h/day), and the break is re-introduced as a clock
window pair, `break_start_time`/`break_end_time`, replacing `break_minutes`.
"""

from src.app.core.firestore import (
    NAMESPACE_SETTINGS_COLLECTION,
    SETTINGS_SUBCOLLECTION,
)
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import Role

SETTINGS_URL = "/settings"

# A role NOT permitted to manage settings, used for 403 tests.
FORBIDDEN_ROLE = Role.MAINTENANCE_AGENT.value


def _actor(seed_user, **overrides):
    overrides.setdefault("role", Role.PRODUCTION_SUPERVISOR.value)
    return seed_user(**overrides)


def _stored(fake_db, namespace_id):
    return FirestoreClient(client=fake_db).get_subdocument(
        NAMESPACE_SETTINGS_COLLECTION, namespace_id, SETTINGS_SUBCOLLECTION, namespace_id
    )


def _window(start_time, end_time, break_start_time=None, break_end_time=None):
    """Expected `ShiftTime` JSON shape, break fields defaulting to `None`."""
    return {
        "start_time": start_time,
        "end_time": end_time,
        "break_start_time": break_start_time,
        "break_end_time": break_end_time,
    }


class TestCreateSettings:
    def test_create_single_shift_defaults_escalation(
        self, client, fake_db, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {"start_time": "06:00", "end_time": "14:00"},
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 201, res.text
        data = res.json()["data"]
        assert data["shift_number"] == 1
        assert data["time_to_escalate"] == 1800  # default
        assert data["shift_1"] == _window("06:00", "14:00")

        stored = _stored(fake_db, actor["namespace_id"])
        assert stored["namespace_id"] == actor["namespace_id"]
        assert stored["shift_number"] == 1

    def test_create_single_shift_without_window_is_422(
        self, client, seed_user, auth_headers
    ):
        """Revision 3, §5bis.4bis: the shift window is required starting at
        `shift_number == 1` — a mono-shift plant no longer gets an implicit
        24h/day planned-time fallback silently."""
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL, json={"shift_number": 1}, headers=auth_headers(actor)
        )
        assert res.status_code == 422

    def test_create_multi_shift_with_windows(
        self, client, fake_db, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 2,
                "shift_1": {"start_time": "06:00", "end_time": "14:00"},
                "shift_2": {"start_time": "14:00", "end_time": "22:00"},
                "time_to_escalate": 900,
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 201, res.text
        data = res.json()["data"]
        assert data["shift_1"] == _window("06:00", "14:00")
        assert data["shift_2"] == _window("14:00", "22:00")
        assert data["time_to_escalate"] == 900

    def test_create_shift_with_break_minutes_is_ignored(
        self, client, fake_db, seed_user, auth_headers
    ):
        """`break_minutes` no longer exists on `ShiftTime` — a client still
        sending it gets a normal 201 with the field simply dropped, not a
        validation error."""
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "break_minutes": 30,
                },
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 201, res.text
        data = res.json()["data"]
        assert data["shift_1"] == _window("06:00", "14:00")

        stored = _stored(fake_db, actor["namespace_id"])
        assert "break_minutes" not in stored["shift_1"]

    def test_get_legacy_shift_with_stored_break_minutes_ignores_it(
        self, client, fake_db, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        # Simulate a stored document from before `break_minutes` was removed.
        FirestoreClient(client=fake_db).create_subdocument(
            NAMESPACE_SETTINGS_COLLECTION,
            actor["namespace_id"],
            SETTINGS_SUBCOLLECTION,
            {
                "namespace_id": actor["namespace_id"],
                "shift_number": 1,
                "shift_1": {
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "break_minutes": 30,
                },
                "shift_2": None,
                "shift_3": None,
                "time_to_escalate": 1800,
            },
            document_id=actor["namespace_id"],
        )
        res = client.get(
            f"{SETTINGS_URL}/{actor['namespace_id']}", headers=auth_headers(actor)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["shift_1"] == _window("06:00", "14:00")

    def test_get_legacy_shift_without_break_fields_reads_fine(
        self, client, fake_db, seed_user, auth_headers
    ):
        """A document stored before revision 3 has no `break_start_time`/
        `break_end_time` at all — `_shift_from_stored` must read it back
        with the break simply absent, not raise."""
        actor = _actor(seed_user)
        FirestoreClient(client=fake_db).create_subdocument(
            NAMESPACE_SETTINGS_COLLECTION,
            actor["namespace_id"],
            SETTINGS_SUBCOLLECTION,
            {
                "namespace_id": actor["namespace_id"],
                "shift_number": 1,
                "shift_1": {"start_time": "06:00", "end_time": "14:00"},
                "shift_2": None,
                "shift_3": None,
                "time_to_escalate": 1800,
            },
            document_id=actor["namespace_id"],
        )
        res = client.get(
            f"{SETTINGS_URL}/{actor['namespace_id']}", headers=auth_headers(actor)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["shift_1"]["start_time"] == "06:00"
        assert data["shift_1"]["break_start_time"] is None
        assert data["shift_1"]["break_end_time"] is None

    def test_get_legacy_shift_amputated_of_start_and_end_time_is_ignored_not_500(
        self, client, fake_db, seed_user, auth_headers
    ):
        """Review fix W6: a stored shift missing `start_time`/`end_time`
        entirely (e.g. a document that only ever carried `break_minutes`)
        used to re-validate against `ShiftTime`'s own field constraints
        (`pattern`, zero-length rejection) and raise an uncaught
        `pydantic.ValidationError` -> 500. It must now degrade to "not
        configured" instead, exactly like the KPI module's `_parse_hhmm`
        (fix #9) tolerates the same class of corrupted document."""
        actor = _actor(seed_user)
        FirestoreClient(client=fake_db).create_subdocument(
            NAMESPACE_SETTINGS_COLLECTION,
            actor["namespace_id"],
            SETTINGS_SUBCOLLECTION,
            {
                "namespace_id": actor["namespace_id"],
                "shift_number": 1,
                "shift_1": {"break_minutes": 30},
                "shift_2": None,
                "shift_3": None,
                "time_to_escalate": 1800,
            },
            document_id=actor["namespace_id"],
        )
        res = client.get(
            f"{SETTINGS_URL}/{actor['namespace_id']}", headers=auth_headers(actor)
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["shift_1"] is None

    def test_create_multi_shift_missing_window_is_422(
        self, client, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 2,
                "shift_1": {"start_time": "06:00", "end_time": "14:00"},
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 422

    def test_create_invalid_time_format_is_422(
        self, client, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {"start_time": "6am", "end_time": "14:00"},
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 422

    def test_create_forbidden_role_is_403(self, client, seed_user, auth_headers):
        actor = seed_user(role=FORBIDDEN_ROLE)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {"start_time": "06:00", "end_time": "14:00"},
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 403


class TestBreakWindows:
    """Revision 3, §5bis.4bis: break given as `break_start_time`/
    `break_end_time`, all-or-nothing, contained in the shift window."""

    def test_create_shift_with_valid_break(self, client, fake_db, seed_user, auth_headers):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "break_start_time": "10:00",
                    "break_end_time": "10:30",
                },
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 201, res.text
        data = res.json()["data"]
        assert data["shift_1"] == {
            "start_time": "06:00",
            "end_time": "14:00",
            "break_start_time": "10:00",
            "break_end_time": "10:30",
        }

    def test_break_start_without_break_end_is_422(self, client, seed_user, auth_headers):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "break_start_time": "10:00",
                },
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 422

    def test_break_end_without_break_start_is_422(self, client, seed_user, auth_headers):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "break_end_time": "10:30",
                },
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 422

    def test_break_outside_shift_window_is_422(self, client, seed_user, auth_headers):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "break_start_time": "15:00",
                    "break_end_time": "15:30",
                },
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 422

    def test_break_as_long_as_shift_window_is_422(self, client, seed_user, auth_headers):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "break_start_time": "06:00",
                    "break_end_time": "14:00",
                },
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 422

    def test_zero_length_break_is_422(self, client, seed_user, auth_headers):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "break_start_time": "10:00",
                    "break_end_time": "10:00",
                },
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 422

    def test_break_across_midnight_in_wrapping_shift(
        self, client, fake_db, seed_user, auth_headers
    ):
        """A 22:00 -> 06:00 shift may have a 01:00 -> 01:30 break — both the
        shift and the break wrap around midnight in the sense that the break
        time-of-day is numerically smaller than the shift's start time."""
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {
                    "start_time": "22:00",
                    "end_time": "06:00",
                    "break_start_time": "01:00",
                    "break_end_time": "01:30",
                },
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 201, res.text
        data = res.json()["data"]
        assert data["shift_1"]["break_start_time"] == "01:00"
        assert data["shift_1"]["break_end_time"] == "01:30"


class TestUpdateSettings:
    def test_patch_merges_only_provided_fields(
        self, client, fake_db, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        client.post(
            SETTINGS_URL,
            json={
                "shift_number": 2,
                "shift_1": {"start_time": "06:00", "end_time": "18:00"},
                "shift_2": {"start_time": "18:00", "end_time": "06:00"},
                "time_to_escalate": 1800,
            },
            headers=auth_headers(actor),
        )

        res = client.patch(
            SETTINGS_URL,
            json={"time_to_escalate": 600},
            headers=auth_headers(actor),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["time_to_escalate"] == 600
        # Untouched fields preserved.
        assert data["shift_number"] == 2
        assert data["shift_1"] == _window("06:00", "18:00")

    def test_patch_can_clear_a_shift_with_explicit_null(
        self, client, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        client.post(
            SETTINGS_URL,
            json={
                "shift_number": 2,
                "shift_1": {"start_time": "06:00", "end_time": "18:00"},
                "shift_2": {"start_time": "18:00", "end_time": "06:00"},
            },
            headers=auth_headers(actor),
        )
        res = client.patch(
            SETTINGS_URL,
            json={"shift_number": 1, "shift_2": None},
            headers=auth_headers(actor),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["shift_number"] == 1
        assert data["shift_2"] is None

    def test_patch_shift_with_break_minutes_is_ignored(
        self, client, fake_db, seed_user, auth_headers
    ):
        """Same drop-unknown-field behavior as create (§5bis.3), exercised
        through PATCH's merge path."""
        actor = _actor(seed_user)
        client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {"start_time": "06:00", "end_time": "14:00"},
            },
            headers=auth_headers(actor),
        )

        res = client.patch(
            SETTINGS_URL,
            json={
                "shift_1": {
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "break_minutes": 45,
                }
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["shift_1"] == _window("06:00", "14:00")

        stored = _stored(fake_db, actor["namespace_id"])
        assert "break_minutes" not in stored["shift_1"]

    def test_patch_raising_shift_number_without_new_window_is_422(
        self, client, seed_user, auth_headers
    ):
        """Revision 3 coherence rule: PATCHing `shift_number` up must also
        supply the newly-required shift's window (checked against the
        merged document, not the payload alone)."""
        actor = _actor(seed_user)
        client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {"start_time": "06:00", "end_time": "14:00"},
            },
            headers=auth_headers(actor),
        )
        res = client.patch(
            SETTINGS_URL,
            json={"shift_number": 2},
            headers=auth_headers(actor),
        )
        assert res.status_code == 422

    def test_patch_lowering_shift_number_stays_valid_when_kept_shift_already_configured(
        self, client, seed_user, auth_headers
    ):
        """Lowering `shift_number` (e.g. 3 -> 1) succeeds as long as the
        shifts that remain required (here just `shift_1`) are already
        configured — no need to resend them."""
        actor = _actor(seed_user)
        client.post(
            SETTINGS_URL,
            json={
                "shift_number": 3,
                "shift_1": {"start_time": "06:00", "end_time": "14:00"},
                "shift_2": {"start_time": "14:00", "end_time": "22:00"},
                "shift_3": {"start_time": "22:00", "end_time": "06:00"},
            },
            headers=auth_headers(actor),
        )
        res = client.patch(
            SETTINGS_URL,
            json={"shift_number": 1},
            headers=auth_headers(actor),
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["shift_number"] == 1

    def test_patch_on_legacy_doc_missing_shift_1_requires_it(
        self, client, fake_db, seed_user, auth_headers
    ):
        """A legacy document created before revision 3 at `shift_number ==
        1` without a `shift_1` window is now incoherent under the revision-3
        rule; any PATCH surfaces that and requires `shift_1` be supplied,
        even a PATCH that doesn't otherwise touch shift fields."""
        actor = _actor(seed_user)
        FirestoreClient(client=fake_db).create_subdocument(
            NAMESPACE_SETTINGS_COLLECTION,
            actor["namespace_id"],
            SETTINGS_SUBCOLLECTION,
            {
                "namespace_id": actor["namespace_id"],
                "shift_number": 1,
                "shift_1": None,
                "shift_2": None,
                "shift_3": None,
                "time_to_escalate": 1800,
            },
            document_id=actor["namespace_id"],
        )
        res = client.patch(
            SETTINGS_URL,
            json={"time_to_escalate": 600},
            headers=auth_headers(actor),
        )
        assert res.status_code == 422

        res = client.patch(
            SETTINGS_URL,
            json={"shift_1": {"start_time": "06:00", "end_time": "14:00"}},
            headers=auth_headers(actor),
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["shift_1"] == _window("06:00", "14:00")

    def test_patch_without_existing_settings_is_404(
        self, client, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        res = client.patch(
            SETTINGS_URL,
            json={"time_to_escalate": 600},
            headers=auth_headers(actor),
        )
        assert res.status_code == 404


class TestGetSettings:
    def test_get_own_namespace_returns_settings(
        self, client, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {"start_time": "06:00", "end_time": "14:00"},
            },
            headers=auth_headers(actor),
        )
        res = client.get(
            f"{SETTINGS_URL}/{actor['namespace_id']}", headers=auth_headers(actor)
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["namespace_id"] == actor["namespace_id"]

    def test_get_before_create_is_404(self, client, seed_user, auth_headers):
        actor = _actor(seed_user)
        res = client.get(
            f"{SETTINGS_URL}/{actor['namespace_id']}", headers=auth_headers(actor)
        )
        assert res.status_code == 404

    def test_get_other_namespace_is_403(self, client, seed_user, auth_headers):
        actor = _actor(seed_user)
        res = client.get(
            f"{SETTINGS_URL}/some-other-namespace", headers=auth_headers(actor)
        )
        assert res.status_code == 403

    def test_get_forbidden_role_is_403(self, client, seed_user, auth_headers):
        actor = seed_user(role=FORBIDDEN_ROLE)
        res = client.get(
            f"{SETTINGS_URL}/{actor['namespace_id']}", headers=auth_headers(actor)
        )
        assert res.status_code == 403
