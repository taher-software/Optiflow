"""Direct unit-style tests for the `add_down_time` async handler:
idempotency and namespace-timezone resolution (things the endpoint tests can't
easily assert through HTTP)."""

import importlib
from datetime import datetime, timedelta

import pytest

from src.app.core.escalation import ScheduleEscalationResult
from src.app.core.firestore import NAMESPACE_COLLECTION
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeType, ProductionScope, Role, WorkstationType

add_down_time_module = importlib.import_module("src.app.async_jobs.add_down_time")
common_module = importlib.import_module("src.app.async_jobs._common")
add_down_time = add_down_time_module.add_down_time

NS = "ns-handler"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    """The handler requires the namespace to exist; tz tests re-seed to set it."""
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


class _EmailSpy:
    """Records every `send_down_time_supervisor_email` call; raises for any
    recipient added to `.fail_for` (set by the test)."""

    def __init__(self):
        self.calls: list[dict] = []
        self.fail_for: set[str] = set()

    def __call__(self, to, language, location, app_url=None):
        self.calls.append({"to": to, "language": language, "location": location})
        if to in self.fail_for:
            raise RuntimeError(f"simulated email failure for {to}")

    def __len__(self):
        return len(self.calls)

    def __getitem__(self, index):
        return self.calls[index]

    def __iter__(self):
        return iter(self.calls)


@pytest.fixture
def email_spy(monkeypatch):
    spy = _EmailSpy()
    monkeypatch.setattr(add_down_time_module, "send_down_time_supervisor_email", spy)
    return spy


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


def test_idempotent_on_repeated_job_id(fake_db, seed_user, push_spy):
    seed_user(
        namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
        online=True, push_token="tok",
    )
    add_down_time(NS, _payload(), "job-1")
    add_down_time(NS, _payload(), "job-1")  # replay

    assert _issue_count(fake_db, NS) == 1
    # Push fired only on the first (real) processing, not the idempotent replay.
    assert len(push_spy) == 1


def test_setup_changeover_department_becomes_process(fake_db, push_spy):
    add_down_time(
        NS,
        _payload(
            down_time_type=DownTimeType.SETUP_CHANGEOVER.value,
            department="production",
        ),
        "job-setup",
    )
    issue = _issue(fake_db, NS, "job-setup")
    assert issue["process"] == "production"
    assert issue["department"] == "production"


def test_created_at_uses_namespace_timezone(fake_db, seed_namespace, push_spy):
    seed_namespace(id=NS, timezone="Europe/Paris")
    add_down_time(NS, _payload(), "job-tz")
    issue = _issue(fake_db, NS, "job-tz")
    # Paris is +01:00 / +02:00 — never UTC.
    offset = datetime.fromisoformat(issue["created_at"]).utcoffset()
    assert offset is not None and offset != timedelta(0)


def test_created_at_defaults_to_utc_when_timezone_missing(
    fake_db, seed_namespace, push_spy
):
    seed_namespace(id=NS, timezone=None)
    add_down_time(NS, _payload(), "job-utc")
    issue = _issue(fake_db, NS, "job-utc")
    offset = datetime.fromisoformat(issue["created_at"]).utcoffset()
    assert offset == timedelta(0)


# --------------------------------------------------------------------------- #
# Production-supervisor notifications (OTHERS only)
# --------------------------------------------------------------------------- #


class TestSupervisorNotifications:
    def test_others_type_notifies_agents_and_all_supervisors(
        self, fake_db, seed_user, push_spy, email_spy
    ):
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            online=True, push_token="tok-agent",
        )
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_SUPERVISOR.value,
            online=True, push_token="tok-sup-online", email="sup-online@example.com",
        )
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_SUPERVISOR.value,
            online=False, push_token="tok-sup-offline", email="sup-offline@example.com",
        )

        result = add_down_time(
            NS, _payload(down_time_type=DownTimeType.OTHERS.value), "job-others"
        )
        assert result == {"status": "created", "down_time_id": "job-others"}

        issue = _issue(fake_db, NS, "job-others")
        assert issue["process"] == "production"

        # Two push calls: one for the process agent(s), one for supervisors.
        assert len(push_spy) == 2
        all_tokens = [set(c["tokens"]) for c in push_spy]
        assert {"tok-agent"} in all_tokens
        # Deliberately includes the offline supervisor.
        assert {"tok-sup-online", "tok-sup-offline"} in all_tokens

        # Both supervisors get an email, including the offline one.
        assert {c["to"] for c in email_spy} == {
            "sup-online@example.com",
            "sup-offline@example.com",
        }

    def test_non_others_type_sends_no_supervisor_notifications(
        self, seed_user, push_spy, email_spy
    ):
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok-agent",
        )
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_SUPERVISOR.value,
            online=True, push_token="tok-sup", email="sup@example.com",
        )

        add_down_time(
            NS, _payload(down_time_type=DownTimeType.BREAKDOWN.value), "job-breakdown"
        )

        # Only the agent-notification push fires; no supervisor push/email.
        assert len(push_spy) == 1
        assert set(push_spy[0]["tokens"]) == {"tok-agent"}
        assert len(email_spy) == 0

    def test_supervisors_in_other_namespace_are_never_notified(
        self, seed_namespace, seed_user, push_spy, email_spy
    ):
        seed_namespace(id="other-ns")
        seed_user(
            namespace_id="other-ns", role=Role.PRODUCTION_SUPERVISOR.value,
            online=True, push_token="tok-other-ns", email="other-ns-sup@example.com",
        )

        add_down_time(
            NS, _payload(down_time_type=DownTimeType.OTHERS.value), "job-tenant-scope"
        )

        all_tokens = {t for c in push_spy for t in c["tokens"]}
        assert "tok-other-ns" not in all_tokens
        assert "other-ns-sup@example.com" not in {c["to"] for c in email_spy}

    def test_supervisor_without_email_skipped_for_email_but_still_gets_push(
        self, seed_user, push_spy, email_spy
    ):
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_SUPERVISOR.value,
            online=True, push_token="tok-sup-no-email", email=None,
        )

        add_down_time(
            NS, _payload(down_time_type=DownTimeType.OTHERS.value), "job-no-email"
        )

        supervisor_call = next(
            c for c in push_spy if "tok-sup-no-email" in c["tokens"]
        )
        assert "tok-sup-no-email" in supervisor_call["tokens"]
        assert len(email_spy) == 0

    def test_email_failure_for_one_recipient_does_not_block_others_or_job(
        self, seed_user, push_spy, email_spy
    ):
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_SUPERVISOR.value,
            email="fails@example.com", push_token="t1",
        )
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_SUPERVISOR.value,
            email="ok@example.com", push_token="t2",
        )
        email_spy.fail_for.add("fails@example.com")

        result = add_down_time(
            NS, _payload(down_time_type=DownTimeType.OTHERS.value), "job-email-fail"
        )

        # Both recipients were attempted despite the first one raising, and
        # the job still reports success (no retry triggered).
        assert {c["to"] for c in email_spy} == {"fails@example.com", "ok@example.com"}
        assert result == {"status": "created", "down_time_id": "job-email-fail"}


# --------------------------------------------------------------------------- #
# Bilingual notification copy, driven by the namespace's `language` field
# --------------------------------------------------------------------------- #


class TestNotificationLanguage:
    def test_french_namespace_produces_french_push_copy(
        self, seed_namespace, seed_user, push_spy
    ):
        seed_namespace(id=NS, language="fr")
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS, _payload(down_time_type=DownTimeType.BREAKDOWN.value), "job-fr"
        )
        assert push_spy[0]["title"] == "Nouvel arrêt déclaré"

    def test_english_namespace_produces_english_push_copy(
        self, seed_namespace, seed_user, push_spy
    ):
        seed_namespace(id=NS, language="en")
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS, _payload(down_time_type=DownTimeType.BREAKDOWN.value), "job-en"
        )
        assert push_spy[0]["title"] == "New downtime ticket"

    def test_namespace_without_language_field_produces_english_push_copy(
        self, fake_db, seed_user, push_spy
    ):
        legacy_ns = "ns-legacy-no-language"
        # Simulates a pre-migration namespace document (schemaless Firestore,
        # no `language` key at all — not even `None`).
        fake_db.collection(NAMESPACE_COLLECTION).document(legacy_ns).set(
            {"id": legacy_ns, "company_name": "Legacy Co"}
        )
        seed_user(
            namespace_id=legacy_ns, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            legacy_ns, _payload(down_time_type=DownTimeType.BREAKDOWN.value), "job-legacy"
        )
        assert push_spy[0]["title"] == "New downtime ticket"


# --------------------------------------------------------------------------- #
# `_resolve_location`
# --------------------------------------------------------------------------- #


class TestResolveLocation:
    def test_work_station_scope_uses_workstation_name(
        self, seed_user, seed_workstation, push_spy
    ):
        station = seed_workstation(namespace_id=NS, name="Station 7")
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=station["id"],
            ),
            "job-ws-location",
        )
        assert "Station 7" in push_spy[0]["body"]

    def test_production_line_scope_uses_line_name(
        self, seed_user, seed_production_line, push_spy
    ):
        line = seed_production_line(namespace_id=NS, name="Line A")
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.PRODUCTION_LINE.value,
                production_line_id=line["id"],
            ),
            "job-line-location",
        )
        assert "Line A" in push_spy[0]["body"]

    def test_uap_scope_uses_uap_name(self, seed_user, seed_uap, push_spy):
        uap = seed_uap(namespace_id=NS, name="UAP North")
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS,
            _payload(production_scope=ProductionScope.UAP.value, uap_id=uap["id"]),
            "job-uap-location",
        )
        assert "UAP North" in push_spy[0]["body"]

    def test_plant_scope_uses_namespace_company_name(
        self, seed_namespace, seed_user, push_spy
    ):
        seed_namespace(id=NS, company_name="Acme Plant")
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS,
            _payload(production_scope=ProductionScope.PLANT.value),
            "job-plant-location",
        )
        assert "Acme Plant" in push_spy[0]["body"]

    def test_cross_tenant_workstation_never_leaks_its_name(
        self, seed_namespace, seed_user, seed_workstation, push_spy
    ):
        # A forged/stale job message could pair this tenant's namespace_id
        # with another tenant's workstation_id. The victim's workstation name
        # must never leak into this tenant's notification copy.
        seed_namespace(id=NS, company_name="Acme Plant")
        other_station = seed_workstation(namespace_id="other-ns", name="Victim Station")
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        result = add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=other_station["id"],
            ),
            "job-cross-tenant-location",
        )
        assert result == {"status": "created", "down_time_id": "job-cross-tenant-location"}
        assert "Victim Station" not in push_spy[0]["body"]
        assert "Acme Plant" in push_spy[0]["body"]

    def test_missing_referenced_document_falls_back_to_company_name(
        self, fake_db, seed_namespace, seed_user, push_spy
    ):
        seed_namespace(id=NS, company_name="Acme Plant")
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        result = add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id="does-not-exist",
            ),
            "job-missing-doc",
        )
        assert result == {"status": "created", "down_time_id": "job-missing-doc"}
        assert "Acme Plant" in push_spy[0]["body"]
        assert _issue(fake_db, NS, "job-missing-doc") is not None


# --------------------------------------------------------------------------- #
# Idempotent replay sends no notifications at all
# --------------------------------------------------------------------------- #


def test_notification_phase_failure_does_not_fail_or_retry_the_job(
    fake_db, monkeypatch
):
    """A transient failure while resolving notification recipients must not
    propagate: the ticket is already written, and a retry would just hit the
    idempotency guard and notify nobody. The job must still report success
    and the issue must exist."""

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated transient Firestore error")

    monkeypatch.setattr(add_down_time_module, "_notify_process_agents", _boom)

    result = add_down_time(NS, _payload(), "job-notify-fails")

    assert result == {"status": "created", "down_time_id": "job-notify-fails"}
    assert _issue(fake_db, NS, "job-notify-fails") is not None


def test_idempotent_replay_sends_no_notifications(
    seed_user, push_spy, email_spy
):
    seed_user(
        namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
        online=True, push_token="tok-agent",
    )
    seed_user(
        namespace_id=NS, role=Role.PRODUCTION_SUPERVISOR.value,
        online=True, push_token="tok-sup", email="sup@example.com",
    )

    add_down_time(NS, _payload(down_time_type=DownTimeType.OTHERS.value), "job-replay")
    assert len(push_spy) == 2
    assert len(email_spy) == 1

    push_spy.clear()
    result = add_down_time(
        NS, _payload(down_time_type=DownTimeType.OTHERS.value), "job-replay"
    )
    assert result == {
        "status": "skipped",
        "reason": "already processed",
        "down_time_id": "job-replay",
    }
    assert push_spy == []
    assert len(email_spy) == 1  # unchanged — no new email sent on replay


# --------------------------------------------------------------------------- #
# First escalation cycle scheduling (`should_escalate` -> `schedule_escalation`)
# --------------------------------------------------------------------------- #


@pytest.fixture
def schedule_escalation_spy(monkeypatch):
    """Spy on `_common.schedule_escalation` — the innermost primitive call
    `_common.schedule_escalation_cycle` makes (the shared composition both
    handlers call; patching it here, not `schedule_escalation_cycle` itself,
    lets the REAL composition run — id derivation, the write-on-success-only
    Firestore persist — against a fake network call). Records every call
    including the `task_id`/`escalation_number` it's invoked with, and
    always succeeds by echoing the `task_id` back."""
    calls: list[dict] = []

    def _spy(namespace_id, down_time_id, timezone_name, task_id=None, escalation_number=None):
        calls.append(
            {
                "namespace_id": namespace_id,
                "down_time_id": down_time_id,
                "timezone_name": timezone_name,
                "task_id": task_id,
                "escalation_number": escalation_number,
            }
        )
        return ScheduleEscalationResult(task_id=task_id, already_existed=False)

    monkeypatch.setattr(common_module, "schedule_escalation", _spy)
    return calls


@pytest.fixture
def schedule_escalation_cycle_spy(monkeypatch):
    """Full-replacement spy on `add_down_time_module.schedule_escalation_cycle`
    (the imported name the handler calls) — used only to prove `add_down_time`
    goes through the ONE shared composition, with the exact args it's called
    with. Does NOT execute the real composition (no Firestore write happens)
    — use `schedule_escalation_spy` instead for tests needing real persisted
    state."""
    calls: list[dict] = []

    def _spy(firestore, namespace_id, namespace, down_time_id, escalation_number):
        calls.append(
            {
                "namespace_id": namespace_id,
                "namespace": namespace,
                "down_time_id": down_time_id,
                "escalation_number": escalation_number,
            }
        )
        return f"{down_time_id}-{escalation_number}"

    monkeypatch.setattr(add_down_time_module, "schedule_escalation_cycle", _spy)
    return calls


class TestEscalationScheduling:
    def test_standard_workstation_does_not_schedule_escalation(
        self, seed_user, seed_workstation, push_spy, schedule_escalation_spy
    ):
        station = seed_workstation(namespace_id=NS, type=WorkstationType.STANDARD.value)
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=station["id"],
            ),
            "job-standard-ws",
        )
        assert schedule_escalation_spy == []

    def test_missing_workstation_document_does_not_escalate(
        self, seed_user, push_spy, schedule_escalation_spy
    ):
        """Fail-closed: a work-station-scoped ticket referencing a
        nonexistent workstation id must never escalate on unclear data."""
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id="does-not-exist",
            ),
            "job-missing-workstation",
        )
        assert schedule_escalation_spy == []

    def test_bottleneck_workstation_schedules_escalation(
        self, fake_db, seed_user, seed_workstation, push_spy, schedule_escalation_spy
    ):
        station = seed_workstation(namespace_id=NS, type=WorkstationType.BOTTLENECK.value)
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=station["id"],
            ),
            "job-bottleneck-ws",
        )
        assert len(schedule_escalation_spy) == 1
        assert schedule_escalation_spy[0]["down_time_id"] == "job-bottleneck-ws"
        issue = _issue(fake_db, NS, "job-bottleneck-ws")
        assert issue["escalation_task_id"] == schedule_escalation_spy[0]["task_id"]

    def test_plant_scoped_ticket_schedules_escalation(
        self, fake_db, seed_user, push_spy, schedule_escalation_spy
    ):
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS, _payload(production_scope=ProductionScope.PLANT.value), "job-plant"
        )
        assert len(schedule_escalation_spy) == 1
        issue = _issue(fake_db, NS, "job-plant")
        assert issue["escalation_task_id"] == schedule_escalation_spy[0]["task_id"]

    def test_critical_workstation_schedules_escalation(
        self, fake_db, seed_user, seed_workstation, push_spy, schedule_escalation_spy
    ):
        station = seed_workstation(namespace_id=NS, type=WorkstationType.CRITICAL.value)
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS,
            _payload(
                production_scope=ProductionScope.WORK_STATION.value,
                workstation_id=station["id"],
            ),
            "job-critical-ws",
        )
        assert len(schedule_escalation_spy) == 1

    def test_namespace_timezone_forwarded_to_schedule_escalation(
        self, seed_namespace, seed_user, push_spy, schedule_escalation_spy
    ):
        seed_namespace(id=NS, timezone="Europe/Paris")
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )
        add_down_time(
            NS, _payload(production_scope=ProductionScope.PLANT.value), "job-plant-tz"
        )
        assert schedule_escalation_spy[0]["timezone_name"] == "Europe/Paris"

    def test_first_cycle_id_is_deterministic_job_id_dash_one(
        self, fake_db, seed_user, push_spy, schedule_escalation_spy
    ):
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )

        add_down_time(
            NS, _payload(production_scope=ProductionScope.PLANT.value), "job-first-cycle"
        )

        assert schedule_escalation_spy[0]["task_id"] == "job-first-cycle-1"
        assert schedule_escalation_spy[0]["escalation_number"] == 1
        issue = _issue(fake_db, NS, "job-first-cycle")
        assert issue["escalation_task_id"] == "job-first-cycle-1"

    def test_failed_first_cycle_scheduling_does_not_persist_a_task_id_or_fail_ticket_creation(
        self, fake_db, seed_user, push_spy, monkeypatch
    ):
        monkeypatch.setattr(
            common_module, "schedule_escalation",
            lambda *a, **k: ScheduleEscalationResult(task_id=None, already_existed=False),
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )

        result = add_down_time(
            NS, _payload(production_scope=ProductionScope.PLANT.value), "job-schedule-fails"
        )

        # Ticket creation is unaffected: the job still reports success. Since
        # `schedule_escalation` itself returned falsy (creation failed), the
        # shared composition never writes escalation bookkeeping to the
        # issue at all — this handler's own retry cannot help here (a retry
        # would just hit the idempotency guard and return early), so the
        # ticket ends up with NO escalation chain at all, which is the
        # accepted, documented limitation (see the module docstring).
        assert result == {"status": "created", "down_time_id": "job-schedule-fails"}
        issue = _issue(fake_db, NS, "job-schedule-fails")
        assert "escalation_task_id" not in issue
        assert "escalation_count" not in issue
        assert "escalated_at" not in issue

    def test_goes_through_the_shared_schedule_escalation_cycle_function(
        self, seed_user, push_spy, schedule_escalation_cycle_spy
    ):
        """Proves the `should_escalate` block calls the ONE shared
        composition (`_common.schedule_escalation_cycle`) for cycle 1, not
        some inline reimplementation."""
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )

        add_down_time(
            NS, _payload(production_scope=ProductionScope.PLANT.value), "job-shared-fn"
        )

        assert len(schedule_escalation_cycle_spy) == 1
        call = schedule_escalation_cycle_spy[0]
        assert call["namespace_id"] == NS
        assert call["down_time_id"] == "job-shared-fn"
        assert call["escalation_number"] == 1

    def test_none_return_from_schedule_escalation_leaves_the_issue_unwritten(
        self, fake_db, seed_user, push_spy, monkeypatch
    ):
        """`schedule_escalation` returning `None` (Cloud Tasks creation
        failed) must leave the newly-created issue document with NO
        escalation bookkeeping at all — not merely "no exception raised"."""
        monkeypatch.setattr(
            common_module, "schedule_escalation",
            lambda *a, **k: ScheduleEscalationResult(task_id=None, already_existed=False),
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )

        add_down_time(
            NS, _payload(production_scope=ProductionScope.PLANT.value), "job-none-unwritten"
        )

        issue = _issue(fake_db, NS, "job-none-unwritten")
        assert "escalation_task_id" not in issue
        assert "escalation_count" not in issue
        assert "escalated_at" not in issue

    def test_already_existed_true_performs_zero_firestore_writes(
        self, fake_db, seed_user, push_spy, monkeypatch
    ):
        """`already_existed=True` must be treated the same as the `None`
        case for write purposes: no escalation bookkeeping written to the
        issue at all (unlike `escalate_down_time`, `add_down_time` never had
        a pre-existing document to leave "unchanged" — the assertion here is
        that NOTHING escalation-related gets added)."""
        monkeypatch.setattr(
            common_module, "schedule_escalation",
            lambda *a, **k: ScheduleEscalationResult(
                task_id="job-already-existed-1", already_existed=True
            ),
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok",
        )

        add_down_time(
            NS, _payload(production_scope=ProductionScope.PLANT.value), "job-already-existed"
        )

        issue = _issue(fake_db, NS, "job-already-existed")
        assert "escalation_task_id" not in issue
        assert "escalation_count" not in issue
        assert "escalated_at" not in issue
