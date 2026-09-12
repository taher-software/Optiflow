"""`add_down_time` handler — the defensive re-check half of the
single-open-downtime guard, per `.claude/specs/downtime-gantt.md` §4 rev2:

"checked synchronously in the endpoint's service (so the caller gets the
409), and re-checked defensively in the `add_down_time` async handler,
which aborts without creating the ticket when the conflict exists (the
endpoint only publishes; it never runs the handler in-process)."

Conflict definition (§4, revised 2026-09-11): the handler must abort when
the **target resource or any of its ancestors** (workstation -> its line ->
its UAP -> plant) already carries an issue in status `pending` or `ongoing`.
A `resolved` (not yet closed) ticket does not block. An unrelated resource in
another branch of the hierarchy does not block either. The reverse direction
— declaring a *parent* while a *child* is down — stays allowed.

None of this exists yet — today `add_down_time` only guards against
replaying the SAME `job_id` (see `tests/async_jobs/test_add_down_time.py`),
never against a DIFFERENT job_id landing on a resource (or one of its
ancestors) that already has an open ticket. Every "should now be blocked"
test below is expected to fail on its own assertion (a second issue document
gets created, where none should be) rather than on a broken fixture. The
"still allowed" tests assert behavior that already holds today and are not
expected to fail — they pin the non-regression half of the contract once the
guard lands.

**rev4** (review finding W5): `/pubsub_job` is unauthenticated by design and
recopies the payload unvalidated, so the handler must not simply pass a
payload-supplied `production_line_id`/`uap_id` straight through — it must
resolve the ancestor chain from the Firestore resource documents themselves
(`workstation_id` -> `production_line_id` -> `uap_id`), the same way it
already does when those ids are *missing*. `TestConflictGuardDoesNotTrustPayload`
pins this: a payload naming the right `workstation_id` but the WRONG
`production_line_id` for it, while the workstation's REAL line carries an
open ticket, must still be aborted.

Ancestor ids are resolved from the resource documents themselves (workstation
-> `production_line_id` -> uap -> namespace), never from the payload: the
existing handler suite already establishes that a `work station`-scoped
payload only ever carries `workstation_id` (see
`test_add_down_time.py::TestResolveLocation`), so this guard's ancestor walk
must read the seeded workstation/production_line docs, exactly like
`_resolve_location` already does for notification copy.

The publisher is never invoked here — per convention, the handler is called
directly with its payload, never through Pub/Sub (see `.claude/skills/test`
"Async handler tests")."""

import importlib
import uuid

import pytest

from src.app.globals.enum import DownTimeStatus, DownTimeType, ProductionScope
from src.app.gcp.firestore import FirestoreClient

add_down_time_module = importlib.import_module("src.app.async_jobs.add_down_time")
add_down_time = add_down_time_module.add_down_time

NS = "ns-handler-conflict-guard"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS)


@pytest.fixture
def push_spy(monkeypatch):
    calls: list[dict] = []

    def _spy(tokens, title, body, data=None):
        calls.append(
            {"tokens": list(tokens), "title": title, "body": body, "data": data}
        )

    monkeypatch.setattr(add_down_time_module, "send_push_notifications", _spy)
    return calls


def _issue(fake_db, namespace_id, job_id):
    return FirestoreClient(client=fake_db).get_subdocument(
        "down_time", namespace_id, "issues", job_id
    )


def _issue_count(fake_db, namespace_id):
    return len(
        FirestoreClient(client=fake_db).find_subdocuments(
            "down_time", namespace_id, "issues"
        )
    )


def _payload(**overrides):
    base = {
        "created_by": "creator-1",
        "production_scope": ProductionScope.PLANT.value,
        "down_time_type": DownTimeType.BREAKDOWN.value,
    }
    base.update(overrides)
    return base


def _seed_open_issue(fake_db, namespace_id=NS, **overrides):
    """A pre-existing issue document, written straight into `fake_db` (not
    through the handler) so its `job_id`/`id` is independent of the ticket
    the test declares next."""
    issue_id = overrides.pop("id", str(uuid.uuid4()))
    issue = {
        "id": issue_id,
        "namespace_id": namespace_id,
        "created_at": "2026-01-15T08:00:00+00:00",
        "updated_at": "2026-01-15T08:00:00+00:00",
        "down_time_scope": "plant",
        "uap_id": None,
        "production_line_id": None,
        "workstation_id": None,
        "down_time_type": DownTimeType.BREAKDOWN.value,
        "status": DownTimeStatus.PENDING.value,
        "created_by": "creator-1",
    }
    issue.update(overrides)
    fake_db.collection(DOWN_TIME_COLLECTION).document(namespace_id).collection(
        ISSUES_SUBCOLLECTION
    ).document(issue_id).set(issue)
    return issue


class TestConflictGuardAbortsCreation:
    """§4 rev2 — target resource OR any ancestor with a `pending`/`ongoing`
    ticket aborts the handler's creation, without writing a document."""

    def test_conflicting_resource_aborts_without_creating_ticket(self, fake_db, push_spy):
        """An existing `pending` plant-scope ticket already open (different
        job_id) — a second `plant`-scope declaration must be aborted, not
        written, by the handler's own defensive re-check."""
        add_down_time(NS, _payload(), "job-first")
        assert _issue(fake_db, NS, "job-first") is not None

        add_down_time(NS, _payload(), "job-second")

        assert _issue(fake_db, NS, "job-second") is None
        assert _issue_count(fake_db, NS) == 1

    def test_open_plant_ticket_blocks_uap_declaration(
        self, fake_db, push_spy, seed_uap
    ):
        uap = seed_uap(namespace_id=NS)
        _seed_open_issue(fake_db, down_time_scope="plant", status=DownTimeStatus.PENDING.value)

        add_down_time(
            NS,
            _payload(production_scope=ProductionScope.UAP.value, uap_id=uap["id"]),
            "job-uap",
        )

        assert _issue(fake_db, NS, "job-uap") is None
        assert _issue_count(fake_db, NS) == 1

    def test_open_plant_ticket_blocks_line_declaration(
        self, fake_db, push_spy, seed_uap, seed_production_line
    ):
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        _seed_open_issue(fake_db, down_time_scope="plant", status=DownTimeStatus.ONGOING.value)

        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.PRODUCTION_LINE.value,
                production_line_id=line["id"],
            ),
            "job-line",
        )

        assert _issue(fake_db, NS, "job-line") is None
        assert _issue_count(fake_db, NS) == 1

    def test_open_plant_ticket_blocks_workstation_declaration(
        self, fake_db, push_spy, seed_uap, seed_production_line, seed_workstation
    ):
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_open_issue(fake_db, down_time_scope="plant", status=DownTimeStatus.PENDING.value)

        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=station["id"],
            ),
            "job-station",
        )

        assert _issue(fake_db, NS, "job-station") is None
        assert _issue_count(fake_db, NS) == 1

    def test_open_uap_ticket_blocks_line_declaration(
        self, fake_db, push_spy, seed_uap, seed_production_line
    ):
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        _seed_open_issue(
            fake_db, down_time_scope="uap", uap_id=uap["id"], status=DownTimeStatus.PENDING.value
        )

        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.PRODUCTION_LINE.value,
                production_line_id=line["id"],
            ),
            "job-line-under-uap",
        )

        assert _issue(fake_db, NS, "job-line-under-uap") is None
        assert _issue_count(fake_db, NS) == 1

    def test_open_uap_ticket_blocks_workstation_declaration(
        self, fake_db, push_spy, seed_uap, seed_production_line, seed_workstation
    ):
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_open_issue(
            fake_db, down_time_scope="uap", uap_id=uap["id"], status=DownTimeStatus.ONGOING.value
        )

        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=station["id"],
            ),
            "job-station-under-uap",
        )

        assert _issue(fake_db, NS, "job-station-under-uap") is None
        assert _issue_count(fake_db, NS) == 1

    def test_open_line_ticket_blocks_workstation_declaration(
        self, fake_db, push_spy, seed_uap, seed_production_line, seed_workstation
    ):
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            uap_id=uap["id"],
            status=DownTimeStatus.ONGOING.value,
        )

        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=station["id"],
            ),
            "job-station-under-line",
        )

        assert _issue(fake_db, NS, "job-station-under-line") is None
        assert _issue_count(fake_db, NS) == 1


class TestConflictGuardAllowsCreation:
    """§4 rev2 — resolved/closed ancestor tickets, unrelated branches, and
    the reverse (parent-while-child-down) direction never block the
    handler's creation."""

    def test_no_conflict_creates_the_ticket_normally(self, fake_db, push_spy):
        """Sanity check on the guard's own scope-matching: an unrelated
        workstation-scoped ticket does not block a plant-scoped one."""
        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id="station-unrelated",
            ),
            "job-first",
        )
        add_down_time(NS, _payload(), "job-second")

        assert _issue(fake_db, NS, "job-first") is not None
        assert _issue(fake_db, NS, "job-second") is not None
        assert _issue_count(fake_db, NS) == 2

    def test_resolved_ancestor_ticket_does_not_block(
        self, fake_db, push_spy, seed_uap, seed_production_line, seed_workstation
    ):
        """A `resolved` (not yet closed) ticket on the parent line does not
        block a declaration on one of its workstations — the fix is done."""
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            uap_id=uap["id"],
            status=DownTimeStatus.RESOLVED.value,
        )

        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=station["id"],
            ),
            "job-resolved-ancestor",
        )

        assert _issue(fake_db, NS, "job-resolved-ancestor") is not None
        assert _issue_count(fake_db, NS) == 2

    def test_unrelated_branch_ticket_does_not_block(
        self, fake_db, push_spy, seed_uap, seed_production_line, seed_workstation
    ):
        """An open ticket on a line in a DIFFERENT UAP branch of the
        hierarchy does not block a declaration on an unrelated
        workstation."""
        busy_uap = seed_uap(namespace_id=NS)
        busy_line = seed_production_line(namespace_id=NS, uap_id=busy_uap["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=busy_line["id"],
            uap_id=busy_uap["id"],
            status=DownTimeStatus.ONGOING.value,
        )
        other_uap = seed_uap(namespace_id=NS)
        other_line = seed_production_line(namespace_id=NS, uap_id=other_uap["id"])
        other_station = seed_workstation(namespace_id=NS, production_line_id=other_line["id"])

        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=other_station["id"],
            ),
            "job-unrelated-branch",
        )

        assert _issue(fake_db, NS, "job-unrelated-branch") is not None
        assert _issue_count(fake_db, NS) == 2

    def test_declaring_parent_while_child_down_is_allowed(
        self, fake_db, push_spy, seed_uap, seed_production_line, seed_workstation
    ):
        """Reverse direction: a workstation already down does not block
        declaring a downtime on its parent line — a broader stop is new
        information, not a duplicate."""
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            production_line_id=line["id"],
            uap_id=uap["id"],
            status=DownTimeStatus.ONGOING.value,
        )

        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.PRODUCTION_LINE.value,
                production_line_id=line["id"],
            ),
            "job-parent-while-child-down",
        )

        assert _issue(fake_db, NS, "job-parent-while-child-down") is not None
        assert _issue_count(fake_db, NS) == 2


class TestConflictGuardDoesNotTrustPayload:
    """§4 rev4 (review finding W5) — `/pubsub_job` is unauthenticated and
    recopies the payload unvalidated, so the handler's defensive re-check
    must resolve the ancestor chain from Firestore, never from a
    payload-supplied ancestor id, whether that id is wrong or simply
    absent."""

    def test_wrong_payload_production_line_id_does_not_bypass_the_real_ancestor_guard(
        self, fake_db, push_spy, seed_uap, seed_production_line, seed_workstation
    ):
        """The workstation's REAL production line (per Firestore) is down.
        The payload names a different, unrelated line for it — the only way
        the guard could still catch this is by resolving the ancestor chain
        from the workstation document itself, not from the payload."""
        uap = seed_uap(namespace_id=NS)
        real_line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        unrelated_line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=real_line["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=real_line["id"],
            uap_id=uap["id"],
            status=DownTimeStatus.ONGOING.value,
        )

        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=station["id"],
                production_line_id=unrelated_line["id"],
                uap_id=uap["id"],
            ),
            "job-wrong-line-id",
        )

        assert _issue(fake_db, NS, "job-wrong-line-id") is None
        assert _issue_count(fake_db, NS) == 1

    def test_wrong_payload_uap_id_does_not_bypass_the_real_ancestor_guard(
        self, fake_db, push_spy, seed_uap, seed_production_line, seed_workstation
    ):
        """Same shape one level up: the payload names the right
        `production_line_id` but the WRONG `uap_id` for it. The real UAP
        (per Firestore, via the line) carries the open ticket."""
        real_uap = seed_uap(namespace_id=NS)
        unrelated_uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=real_uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=real_uap["id"],
            status=DownTimeStatus.PENDING.value,
        )

        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=station["id"],
                production_line_id=line["id"],
                uap_id=unrelated_uap["id"],
            ),
            "job-wrong-uap-id",
        )

        assert _issue(fake_db, NS, "job-wrong-uap-id") is None
        assert _issue_count(fake_db, NS) == 1
