"""Tests for the `escalate_down_time` async handler: the four status
branches, recipient rules (production agents vs management), dedupe,
tenant isolation, reschedule bookkeeping, and the deleted-issue /
closed-ticket terminal paths."""

import importlib
from datetime import datetime, timedelta

import pytest

from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeStatus, Process, ProductionScope, Role

escalate_module = importlib.import_module("src.app.async_jobs.escalate_down_time")
escalate_down_time = escalate_module.escalate_down_time

NS = "ns-escalate-handler"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS)


@pytest.fixture(autouse=True)
def _wire_firestore(fake_db, monkeypatch):
    """`escalate_down_time` holds its own imported reference to
    `get_firestore_client` — patch it directly against the same `fake_db` the
    `fake_db` fixture already wires everything else to."""
    client = FirestoreClient(client=fake_db)
    monkeypatch.setattr(escalate_module, "get_firestore_client", lambda: client)
    return client


@pytest.fixture
def push_spy(monkeypatch):
    calls: list[dict] = []

    def _spy(tokens, title, body, data=None):
        calls.append({"tokens": list(tokens), "title": title, "body": body, "data": data})

    monkeypatch.setattr(escalate_module, "send_push_notifications", _spy)
    return calls


class _EmailSpy:
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, to, language, location, duration, app_url=None):
        self.calls.append(
            {"to": to, "language": language, "location": location, "duration": duration}
        )

    def __len__(self):
        return len(self.calls)

    def __getitem__(self, index):
        return self.calls[index]

    def __iter__(self):
        return iter(self.calls)


@pytest.fixture
def email_spy(monkeypatch):
    spy = _EmailSpy()
    monkeypatch.setattr(escalate_module, "send_down_time_escalation_email", spy)
    return spy


@pytest.fixture
def reschedule_spy(monkeypatch):
    """Spy on `schedule_escalation`, returning a fresh fake task id per call
    so `_reschedule`'s "new id replaces the old one" behavior is observable."""
    calls: list[dict] = []
    counter = {"n": 0}

    def _spy(namespace_id, down_time_id, timezone_name):
        counter["n"] += 1
        calls.append(
            {
                "namespace_id": namespace_id,
                "down_time_id": down_time_id,
                "timezone_name": timezone_name,
            }
        )
        return f"new-task-{counter['n']}"

    monkeypatch.setattr(escalate_module, "schedule_escalation", _spy)
    return calls


def _seed_issue(_wire_firestore, namespace_id=NS, down_time_id="issue-1", **overrides):
    now_iso = datetime.now().isoformat()
    issue = {
        "id": down_time_id,
        "namespace_id": namespace_id,
        "created_at": now_iso,
        "updated_at": now_iso,
        "down_time_scope": ProductionScope.PLANT.value,
        "uap_id": None,
        "production_line_id": None,
        "workstation_id": None,
        "down_time_type": "breakdown",
        "department": None,
        "process": Process.MAINTENANCE.value,
        "status": DownTimeStatus.PENDING.value,
        "created_by": "creator-1",
        "escalation_task_id": "old-task-id",
    }
    issue.update(overrides)
    _wire_firestore.create_subdocument(
        "down_time", namespace_id, "issues", issue, document_id=down_time_id
    )
    return issue


def _issue(_wire_firestore, namespace_id=NS, down_time_id="issue-1"):
    return _wire_firestore.get_subdocument(
        "down_time", namespace_id, "issues", down_time_id
    )


def _payload(**overrides):
    base = {"down_time_id": "issue-1"}
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# closed -> terminal, no notification, no reschedule
# --------------------------------------------------------------------------- #


def test_closed_status_stops_without_notifying_or_rescheduling(
    _wire_firestore, push_spy, email_spy, reschedule_spy
):
    _seed_issue(_wire_firestore, status=DownTimeStatus.CLOSED.value)

    result = escalate_down_time(NS, _payload(), "job-closed")

    assert result == {"status": "stopped", "reason": "closed", "down_time_id": "issue-1"}
    assert push_spy == []
    assert len(email_spy) == 0
    assert reschedule_spy == []


def test_closed_status_clears_escalation_task_id(_wire_firestore):
    _seed_issue(_wire_firestore, status=DownTimeStatus.CLOSED.value)

    escalate_down_time(NS, _payload(), "job-closed-clear")

    issue = _issue(_wire_firestore)
    assert issue["escalation_task_id"] is None


# --------------------------------------------------------------------------- #
# deleted issue -> stops the chain without rescheduling, no error
# --------------------------------------------------------------------------- #


def test_deleted_issue_stops_the_chain_without_rescheduling(reschedule_spy, push_spy, email_spy):
    result = escalate_down_time(NS, _payload(down_time_id="does-not-exist"), "job-deleted")

    assert result["status"] == "stopped"
    assert result["reason"] == "issue not found"
    assert reschedule_spy == []
    assert push_spy == []
    assert len(email_spy) == 0


# --------------------------------------------------------------------------- #
# resolved -> production agents only, push only, no management notification
# --------------------------------------------------------------------------- #


class TestResolvedStatus:
    def test_notifies_only_online_production_agents(
        self, _wire_firestore, seed_user, push_spy, email_spy, reschedule_spy
    ):
        _seed_issue(_wire_firestore, status=DownTimeStatus.RESOLVED.value, resolved_at=datetime.now().isoformat())
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            online=True, push_token="tok-agent",
        )
        # Absent `online` defaults to True and should still be notified.
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            push_token="tok-agent-no-online-field",
        )
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            online=False, push_token="tok-agent-offline",
        )

        result = escalate_down_time(NS, _payload(), "job-resolved")

        assert result["status"] == "escalated"
        assert len(push_spy) == 1
        assert set(push_spy[0]["tokens"]) == {"tok-agent", "tok-agent-no-online-field"}
        assert len(email_spy) == 0

    def test_no_manager_owner_or_supervisor_notification_at_all(
        self, _wire_firestore, seed_user, push_spy, email_spy
    ):
        _seed_issue(_wire_firestore, status=DownTimeStatus.RESOLVED.value, resolved_at=datetime.now().isoformat())
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            online=True, push_token="tok-agent",
        )
        for role in (
            Role.MANAGER.value,
            Role.OWNER.value,
            Role.PRODUCTION_SUPERVISOR.value,
            Role.MAINTENANCE_SUPERVISOR.value,
        ):
            seed_user(
                namespace_id=NS, role=role, online=True,
                push_token=f"tok-{role}", email=f"{role}@example.com",
            )

        escalate_down_time(NS, _payload(), "job-resolved-no-mgmt")

        all_tokens = {t for c in push_spy for t in c["tokens"]}
        assert all_tokens == {"tok-agent"}
        assert len(email_spy) == 0

    def test_missing_resolved_at_handled_gracefully(
        self, _wire_firestore, seed_user, push_spy
    ):
        _seed_issue(_wire_firestore, status=DownTimeStatus.RESOLVED.value, resolved_at=None)
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            online=True, push_token="tok-agent",
        )

        result = escalate_down_time(NS, _payload(), "job-resolved-no-resolved-at")

        assert result["status"] == "escalated"
        assert len(push_spy) == 1

    def test_no_online_agents_still_reschedules(
        self, _wire_firestore, push_spy, reschedule_spy
    ):
        _seed_issue(_wire_firestore, status=DownTimeStatus.RESOLVED.value, resolved_at=datetime.now().isoformat())

        escalate_down_time(NS, _payload(), "job-resolved-no-agents")

        assert push_spy == []
        assert len(reschedule_spy) == 1

    def test_reschedules_and_replaces_task_id_and_increments_count(
        self, _wire_firestore, seed_user, push_spy, reschedule_spy
    ):
        _seed_issue(
            _wire_firestore, status=DownTimeStatus.RESOLVED.value,
            resolved_at=datetime.now().isoformat(), escalation_task_id="old-task-id",
            escalation_count=2,
        )
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            online=True, push_token="tok-agent",
        )

        escalate_down_time(NS, _payload(), "job-resolved-reschedule")

        issue = _issue(_wire_firestore)
        assert issue["escalation_task_id"] == "new-task-1"
        assert issue["escalation_task_id"] != "old-task-id"
        assert issue["escalation_count"] == 3
        assert "escalated_at" in issue and issue["escalated_at"]


# --------------------------------------------------------------------------- #
# pending / ongoing -> management escalation (push + email)
# --------------------------------------------------------------------------- #


class TestPendingOngoingStatus:
    @pytest.mark.parametrize(
        "status", [DownTimeStatus.PENDING.value, DownTimeStatus.ONGOING.value]
    )
    def test_notifies_manager_owner_and_supervisors_push_and_email(
        self, _wire_firestore, seed_user, push_spy, email_spy, reschedule_spy, status
    ):
        _seed_issue(_wire_firestore, status=status, process=Process.MAINTENANCE.value)
        seed_user(
            namespace_id=NS, role=Role.MANAGER.value, online=True,
            push_token="tok-manager", email="manager@example.com",
        )
        seed_user(
            namespace_id=NS, role=Role.OWNER.value, online=True,
            push_token="tok-owner", email="owner@example.com",
        )
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_SUPERVISOR.value, online=True,
            push_token="tok-prod-sup", email="prod-sup@example.com",
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_SUPERVISOR.value, online=True,
            push_token="tok-maint-sup", email="maint-sup@example.com",
        )

        result = escalate_down_time(NS, _payload(), f"job-{status}")

        assert result["status"] == "escalated"
        all_tokens = {t for c in push_spy for t in c["tokens"]}
        assert all_tokens == {
            "tok-manager", "tok-owner", "tok-prod-sup", "tok-maint-sup",
        }
        assert {c["to"] for c in email_spy} == {
            "manager@example.com", "owner@example.com",
            "prod-sup@example.com", "maint-sup@example.com",
        }
        assert len(reschedule_spy) == 1

    def test_offline_management_is_still_notified(
        self, _wire_firestore, seed_user, push_spy, email_spy
    ):
        _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
        seed_user(
            namespace_id=NS, role=Role.MANAGER.value, online=False,
            push_token="tok-manager-offline", email="manager-offline@example.com",
        )

        escalate_down_time(NS, _payload(), "job-offline-mgmt")

        all_tokens = {t for c in push_spy for t in c["tokens"]}
        assert "tok-manager-offline" in all_tokens
        assert "manager-offline@example.com" in {c["to"] for c in email_spy}

    def test_dedupes_when_production_supervisor_and_process_supervisor_coincide(
        self, _wire_firestore, seed_user, push_spy, email_spy
    ):
        # process == production -> "production supervisor" role coincides
        # with Role.PRODUCTION_SUPERVISOR: must get exactly one notification.
        _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value, process=Process.PRODUCTION.value)
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_SUPERVISOR.value, online=True,
            push_token="tok-prod-sup", email="prod-sup@example.com",
        )

        escalate_down_time(NS, _payload(), "job-dedupe")

        all_tokens = [t for c in push_spy for t in c["tokens"]]
        assert all_tokens.count("tok-prod-sup") == 1
        assert [c["to"] for c in email_spy].count("prod-sup@example.com") == 1

    def test_no_email_for_recipient_without_one(
        self, _wire_firestore, seed_user, push_spy, email_spy
    ):
        _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
        seed_user(
            namespace_id=NS, role=Role.MANAGER.value, online=True,
            push_token="tok-manager", email=None,
        )

        escalate_down_time(NS, _payload(), "job-no-email")

        assert len(email_spy) == 0
        all_tokens = {t for c in push_spy for t in c["tokens"]}
        assert "tok-manager" in all_tokens

    def test_reschedules_and_replaces_task_id_and_increments_count(
        self, _wire_firestore, seed_user, reschedule_spy
    ):
        _seed_issue(
            _wire_firestore, status=DownTimeStatus.PENDING.value,
            escalation_task_id="old-task-id", escalation_count=None,
        )
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

        escalate_down_time(NS, _payload(), "job-pending-reschedule")

        issue = _issue(_wire_firestore)
        assert issue["escalation_task_id"] == "new-task-1"
        # Legacy documents lack `escalation_count` (None here) -> defensive
        # `.get(...) or 0` treats it as 0, then increments to 1.
        assert issue["escalation_count"] == 1


# --------------------------------------------------------------------------- #
# Tenant isolation
# --------------------------------------------------------------------------- #


def test_issue_from_another_tenant_is_never_acted_on(
    _wire_firestore, seed_namespace, seed_user, push_spy, email_spy, reschedule_spy
):
    other_ns = "ns-other-escalate"
    seed_namespace(id=other_ns)
    _seed_issue(_wire_firestore, namespace_id=other_ns, down_time_id="victim-issue")
    seed_user(
        namespace_id=other_ns, role=Role.MANAGER.value,
        push_token="tok-victim", email="victim@example.com",
    )

    # Forged/stale message: our namespace_id paired with the victim's issue id.
    result = escalate_down_time(NS, _payload(down_time_id="victim-issue"), "job-cross-tenant")

    assert result["status"] == "stopped"
    assert push_spy == []
    assert len(email_spy) == 0
    assert reschedule_spy == []


# --------------------------------------------------------------------------- #
# Bilingual copy
# --------------------------------------------------------------------------- #


def test_french_namespace_produces_french_escalation_copy(
    seed_namespace, _wire_firestore, seed_user, push_spy
):
    seed_namespace(id=NS, language="fr")
    _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
    seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

    escalate_down_time(NS, _payload(), "job-fr")

    assert "Escalade" in push_spy[0]["title"]


def test_english_namespace_produces_english_resolution_reminder_copy(
    seed_namespace, _wire_firestore, seed_user, push_spy
):
    seed_namespace(id=NS, language="en")
    _seed_issue(_wire_firestore, status=DownTimeStatus.RESOLVED.value, resolved_at=datetime.now().isoformat())
    seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value, push_token="tok")

    escalate_down_time(NS, _payload(), "job-en-resolved")

    assert push_spy[0]["title"] == "Resolution awaiting your confirmation"


# --------------------------------------------------------------------------- #
# Notification/reschedule phase containment
# --------------------------------------------------------------------------- #


def test_notification_phase_failure_does_not_fail_or_retry_the_job(
    _wire_firestore, monkeypatch
):
    _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated transient Firestore error")

    monkeypatch.setattr(escalate_module, "_notify_management", _boom)

    result = escalate_down_time(NS, _payload(), "job-notify-fails")

    assert result["status"] == "escalated"


def test_missing_down_time_id_is_a_functional_error():
    result = escalate_down_time(NS, {}, "job-missing-id")
    assert result["status"] == "skipped"


def test_unknown_namespace_is_a_functional_error():
    result = escalate_down_time("no-such-ns", _payload(), "job-unknown-ns")
    assert result["status"] == "skipped"
