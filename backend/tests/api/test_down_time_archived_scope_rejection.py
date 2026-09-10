"""API tests closing a review gap in `POST /down-times`
(`src/app/routers/down_time/services.py::create_down_time`).

`create_down_time` validates all three possible scope ids — `uap_id`,
`production_line_id`, `workstation_id` — through `_validate_uap`,
`_validate_production_line`, `_validate_workstation` respectively. Only
`_validate_workstation` currently checks `is_active` (see
`tests/api/test_resource_archiving.py::TestTicketRejectedOnArchivedWorkstation`,
which is FROZEN and already covers the workstation case — not duplicated
here). `_validate_uap` and `_validate_production_line` do not call
`is_active` at all, so a ticket scoped to an archived UAP or an archived
production line is wrongly accepted today.

This suite covers the gap for the other two scopes, plus the cascade case
that matters most: archiving a UAP archives its production lines too (see
`TestArchiveUapCascade` in the frozen suite), so a ticket referencing one of
those cascaded lines must be refused even though the line itself was never
archived directly.

`production_scope: "plant"` carries no resource id at all (see
`src/app/globals/enum/production_scope.py` and
`CreateDownTimeIn._validate_scope_id`), so there is nothing to validate for
it and no archived-parent scenario applies — deliberately not tested here.

No real Firestore/network is touched — `get_firestore_client()` is
monkeypatched to an in-memory fake via `tests/conftest.py::fake_db`. No
timestamps are asserted in this file, so time is not frozen.
"""

from src.app.globals.enum import DownTimeType, ProductionScope, Role

DOWN_TIMES_URL = "/down-times"
UAPS_URL = "/uaps"
PRODUCTION_LINES_URL = "/production-lines"

NS = "ns-down-time-archived-scope"


def _owner(seed_user, **overrides):
    overrides.setdefault("namespace_id", NS)
    overrides.setdefault("role", Role.OWNER.value)
    return seed_user(**overrides)


def _agent(seed_user, **overrides):
    """A production agent, the role allowed to declare downtime tickets."""
    overrides.setdefault("namespace_id", NS)
    overrides.setdefault("role", Role.PRODUCTION_AGENT.value)
    return seed_user(**overrides)


class TestTicketRejectedOnArchivedUap:
    """POST /down-times with `production_scope: "uap"` must reject a ticket
    scoped to an archived UAP, the same way `_validate_uap` already rejects
    a nonexistent one."""

    def test_create_ticket_on_archived_uap_returns_422(
        self, client, seed_user, seed_uap, auth_headers, publish_spy
    ):
        owner = _owner(seed_user)
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        response = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.UAP.value,
                "uap_id": uap["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )

        assert response.status_code == 422
        assert len(publish_spy) == 0

    def test_create_ticket_on_active_uap_still_succeeds(
        self, client, seed_user, seed_uap, auth_headers, publish_spy
    ):
        """Non-regression companion: an active (never-archived) UAP must
        still accept a ticket, so the rejection above cannot be satisfied by
        refusing every UAP."""
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)

        response = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.UAP.value,
                "uap_id": uap["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )

        assert response.status_code == 202
        assert len(publish_spy) == 1


class TestTicketRejectedOnArchivedProductionLine:
    """POST /down-times with `production_scope: "production line"` must
    reject a ticket scoped to an archived production line, the same way
    `_validate_production_line` already rejects a nonexistent one."""

    def test_create_ticket_on_archived_production_line_returns_422(
        self, client, seed_user, seed_production_line, auth_headers, publish_spy
    ):
        owner = _owner(seed_user)
        agent = _agent(seed_user)
        line = seed_production_line(namespace_id=NS, uap_id=None)
        client.delete(
            f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner)
        )

        response = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PRODUCTION_LINE.value,
                "production_line_id": line["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )

        assert response.status_code == 422
        assert len(publish_spy) == 0

    def test_create_ticket_on_active_production_line_still_succeeds(
        self, client, seed_user, seed_production_line, auth_headers, publish_spy
    ):
        """Non-regression companion: an active (never-archived) production
        line must still accept a ticket."""
        agent = _agent(seed_user)
        line = seed_production_line(namespace_id=NS, uap_id=None)

        response = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PRODUCTION_LINE.value,
                "production_line_id": line["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )

        assert response.status_code == 202
        assert len(publish_spy) == 1

    def test_create_ticket_on_line_cascade_archived_via_its_uap_returns_422(
        self,
        client,
        seed_user,
        seed_uap,
        seed_production_line,
        auth_headers,
        publish_spy,
    ):
        """The cascade case: archiving a UAP archives its production lines
        (see the frozen `TestArchiveUapCascade`) without ever calling
        `DELETE /production-lines/{id}` directly. A ticket scoped to one of
        those cascade-archived lines must still be refused."""
        owner = _owner(seed_user)
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        response = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PRODUCTION_LINE.value,
                "production_line_id": line["id"],
                "uap_id": uap["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )

        assert response.status_code == 422
        assert len(publish_spy) == 0
