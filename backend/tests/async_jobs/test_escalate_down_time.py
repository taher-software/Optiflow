"""Tests for the `escalate_down_time` async handler: the four status
branches, recipient rules (production agents vs management), dedupe,
tenant isolation, the deterministic-id reschedule contract, the
reschedule-before-notify ordering, and the deleted-issue / closed-ticket
terminal paths."""

import importlib
from datetime import datetime, timedelta

import pytest

from src.app.core.escalation import ScheduleEscalationResult
from src.app.core.push import PushDeliveryError
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeStatus, Process, ProductionScope, Role

escalate_module = importlib.import_module("src.app.async_jobs.escalate_down_time")
common_module = importlib.import_module("src.app.async_jobs._common")
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
    """Spy on `_common.schedule_escalation` — the innermost primitive call
    `_common.schedule_escalation_cycle` makes (the shared composition both
    handlers call; patching it here, not `schedule_escalation_cycle` itself,
    lets the REAL composition run — id derivation, the write-on-success-only
    Firestore persist — against a fake network call). Records every call
    including the `task_id` / `escalation_number` it's invoked with, and
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
    """Full-replacement spy on `escalate_module.schedule_escalation_cycle`
    (the imported name `_reschedule` calls) — used only to prove
    `escalate_down_time` goes through the ONE shared composition, with the
    exact args it's called with. Does NOT execute the real composition (no
    Firestore write happens) — use `reschedule_spy` instead for tests that
    need the real persisted state."""
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

    monkeypatch.setattr(escalate_module, "schedule_escalation_cycle", _spy)
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


# --------------------------------------------------------------------------- #
# Reschedule: deterministic id contract
# --------------------------------------------------------------------------- #


class TestDeterministicReschedule:
    def test_id_is_composed_from_down_time_id_and_escalation_number(
        self, _wire_firestore, seed_user, reschedule_spy, push_spy, email_spy
    ):
        _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

        escalate_down_time(NS, _payload(escalation_number=2), "job-composed-id")

        assert len(reschedule_spy) == 1
        assert reschedule_spy[0]["task_id"] == "issue-1-3"
        assert reschedule_spy[0]["escalation_number"] == 3

        issue = _issue(_wire_firestore)
        assert issue["escalation_task_id"] == "issue-1-3"

    def test_escalation_count_persisted_is_the_cycle_that_just_ran(
        self, _wire_firestore, seed_user, reschedule_spy, push_spy, email_spy
    ):
        _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

        escalate_down_time(NS, _payload(escalation_number=4), "job-count")

        issue = _issue(_wire_firestore)
        # escalation_number=4 means cycle 4 just ran; the NEXT cycle (5) is
        # what gets scheduled/persisted as escalation_task_id, but the
        # persisted `escalation_count` reflects the cycle that just executed.
        assert issue["escalation_count"] == 4
        assert issue["escalation_task_id"] == "issue-1-5"
        assert "escalated_at" in issue and issue["escalated_at"]

    def test_missing_escalation_number_defaults_so_next_cycle_is_one(
        self, _wire_firestore, seed_user, reschedule_spy, push_spy, email_spy
    ):
        """A payload with no `escalation_number` (e.g. a task scheduled
        before this field existed) is tolerated, not a functional error —
        defaults to 0 so the next cycle scheduled is 1."""
        _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

        result = escalate_down_time(NS, _payload(), "job-legacy-payload")

        assert result["status"] == "escalated"
        assert reschedule_spy[0]["task_id"] == "issue-1-1"
        assert reschedule_spy[0]["escalation_number"] == 1

    def test_retry_of_the_same_delivery_reuses_the_identical_id(
        self, _wire_firestore, seed_user, reschedule_spy, push_spy, email_spy
    ):
        """Two separate invocations carrying the SAME `escalation_number`
        (as a redelivery / retry of the same cycle would) must compute the
        exact same deterministic id — proving there is no per-call
        randomness left to fork the chain."""
        _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

        escalate_down_time(NS, _payload(escalation_number=1), "job-retry-a")
        escalate_down_time(NS, _payload(escalation_number=1), "job-retry-b")

        assert len(reschedule_spy) == 2
        assert reschedule_spy[0]["task_id"] == reschedule_spy[1]["task_id"] == "issue-1-2"

    def test_goes_through_the_shared_schedule_escalation_cycle_function(
        self, _wire_firestore, seed_user, schedule_escalation_cycle_spy, push_spy, email_spy
    ):
        """Proves `_reschedule` calls the ONE shared composition
        (`_common.schedule_escalation_cycle`) with the cycle being
        scheduled — `escalation_number + 1` — not some inline reimplementation."""
        _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

        escalate_down_time(NS, _payload(escalation_number=2), "job-shared-fn")

        assert len(schedule_escalation_cycle_spy) == 1
        call = schedule_escalation_cycle_spy[0]
        assert call["namespace_id"] == NS
        assert call["down_time_id"] == "issue-1"
        assert call["escalation_number"] == 3

    def test_none_return_from_schedule_escalation_leaves_the_issue_unwritten(
        self, _wire_firestore, seed_user, monkeypatch, push_spy, email_spy
    ):
        """`schedule_escalation` returning `None` (Cloud Tasks creation
        failed — no task exists) must leave the issue document's escalation
        bookkeeping UNCHANGED, not merely "not raise". The stale
        `escalation_task_id` seeded by `_seed_issue` must survive untouched."""
        _seed_issue(
            _wire_firestore, status=DownTimeStatus.PENDING.value,
            escalation_task_id="old-task-id",
        )
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")
        before = _issue(_wire_firestore)

        monkeypatch.setattr(
            common_module, "schedule_escalation",
            lambda *a, **k: ScheduleEscalationResult(task_id=None, already_existed=False),
        )

        result = escalate_down_time(NS, _payload(), "job-schedule-fails")

        assert result["status"] == "escalated"
        after = _issue(_wire_firestore)
        assert after["escalation_task_id"] == before["escalation_task_id"] == "old-task-id"
        assert after.get("escalation_count") == before.get("escalation_count")
        assert after.get("escalated_at") == before.get("escalated_at")

    def test_already_existed_true_performs_zero_firestore_writes(
        self, _wire_firestore, seed_user, monkeypatch, push_spy, email_spy
    ):
        """`already_existed=True` (a retry landing on the same deterministic
        id, or a tombstoned name) must leave the issue's escalation
        bookkeeping BYTE-FOR-BYTE unchanged, exactly like the `None` case —
        whichever call actually created the task already persisted it."""
        _seed_issue(
            _wire_firestore, status=DownTimeStatus.PENDING.value,
            escalation_task_id="old-task-id", escalation_count=1,
            escalated_at="2020-01-01T00:00:00+00:00",
        )
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")
        before = _issue(_wire_firestore)

        monkeypatch.setattr(
            common_module, "schedule_escalation",
            lambda *a, **k: ScheduleEscalationResult(
                task_id="issue-1-1", already_existed=True
            ),
        )

        result = escalate_down_time(NS, _payload(), "job-already-existed")

        assert result["status"] == "escalated"
        after = _issue(_wire_firestore)
        assert after == before

    def test_already_existed_true_still_returns_the_correct_task_id(
        self, _wire_firestore, seed_user, monkeypatch, push_spy, email_spy
    ):
        _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

        seen = {}

        def _spy(namespace_id, down_time_id, timezone_name, task_id=None, escalation_number=None):
            seen["task_id"] = task_id
            return ScheduleEscalationResult(task_id=task_id, already_existed=True)

        monkeypatch.setattr(common_module, "schedule_escalation", _spy)

        escalate_down_time(NS, _payload(), "job-already-existed-id")

        assert seen["task_id"] == "issue-1-1"

    def test_retry_of_the_same_cycle_writes_exactly_once_across_both_attempts(
        self, _wire_firestore, seed_user, monkeypatch
    ):
        """Simulates the real-world case this whole change targets: a
        `backoff` retry re-enters after a notification failure, lands on the
        same deterministic id, and `schedule_escalation` reports
        `already_existed=True` the second time. The Firestore write must
        happen exactly once — on the (first, creating) attempt — not twice."""
        _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

        attempts = {"n": 0}

        def _spy(namespace_id, down_time_id, timezone_name, task_id=None, escalation_number=None):
            attempts["n"] += 1
            already_existed = attempts["n"] > 1
            return ScheduleEscalationResult(task_id=task_id, already_existed=already_existed)

        monkeypatch.setattr(common_module, "schedule_escalation", _spy)

        write_count = {"n": 0}
        real_update = _wire_firestore.update_subdocument

        def _counting_update(*args, **kwargs):
            write_count["n"] += 1
            return real_update(*args, **kwargs)

        monkeypatch.setattr(_wire_firestore, "update_subdocument", _counting_update)

        # First attempt fails in notification -> `backoff` retries the whole
        # handler; second attempt's reschedule call reports already_existed.
        call_count = {"n": 0}

        def _notify_once_then_ok(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated notification failure")

        monkeypatch.setattr(escalate_module, "_notify_management", _notify_once_then_ok)

        escalate_down_time(NS, _payload(), "job-retry-writes-once")

        assert attempts["n"] == 2
        assert write_count["n"] == 1


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
    seed_namespace, _wire_firestore, seed_user, push_spy, email_spy
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
# Reschedule-before-notify ordering + uncontained retry (this round's fix)
# --------------------------------------------------------------------------- #


def test_reschedule_happens_before_notification(
    _wire_firestore, seed_user, monkeypatch
):
    """Ordering assertion: by the time the notification fan-out runs, the
    next cycle has already been secured (reschedule call already made)."""
    _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
    seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

    call_order = []

    def _reschedule_spy(*args, **kwargs):
        call_order.append("reschedule")
        return "task-id"

    def _notify_spy(*args, **kwargs):
        call_order.append("notify")

    monkeypatch.setattr(escalate_module, "schedule_escalation_cycle", _reschedule_spy)
    monkeypatch.setattr(escalate_module, "_notify_management", _notify_spy)

    escalate_down_time(NS, _payload(), "job-order")

    assert call_order == ["reschedule", "notify"]


def test_notification_failure_now_propagates_and_is_retried(
    _wire_firestore, seed_user, monkeypatch
):
    """This is the behavior the earlier (contained) version of this handler
    got wrong: a real notification failure must retry via `backoff`, not be
    silently swallowed. Prove the handler's own top-level retry actually
    re-invokes the whole run up to `max_tries` (3) attempts."""
    _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
    seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

    calls = {"n": 0}

    def _always_fails(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("simulated notification failure")

    monkeypatch.setattr(escalate_module, "_notify_management", _always_fails)

    # `on_giveup` swallows and returns normally (per the `.claude/skills/async`
    # contract) — the job doesn't raise out to the caller even after
    # exhausting retries, but the notification function was genuinely
    # invoked `max_tries` times, proving the failure was retried, not
    # swallowed on the first attempt.
    escalate_down_time(NS, _payload(), "job-notify-retried")

    assert calls["n"] == 3


def test_total_push_failure_propagates_to_backoff_and_retries(
    _wire_firestore, seed_user, monkeypatch
):
    """`send_push_notifications` now raises `PushDeliveryError` when every
    token in a batch fails (see `core.push`). This call site is NOT
    contained (unlike `add_down_time`'s), so the raise must reach this
    handler's own `backoff` decorator and genuinely retry — mirroring
    `test_notification_failure_now_propagates_and_is_retried` above, but
    proving it end-to-end through the real `send_push_notifications` /
    `PushDeliveryError` contract instead of a generic `RuntimeError`."""
    _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
    seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

    calls = {"n": 0}

    def _always_fails(*args, **kwargs):
        calls["n"] += 1
        raise PushDeliveryError("send_push_notifications: all 1 push send(s) failed.")

    monkeypatch.setattr(escalate_module, "send_push_notifications", _always_fails)

    # `on_giveup` swallows and returns normally — the job doesn't raise out
    # to the caller even after exhausting retries, but
    # `send_push_notifications` was genuinely invoked `max_tries` (3) times.
    escalate_down_time(NS, _payload(), "job-push-total-fail-retried")

    assert calls["n"] == 3


def test_reschedule_still_secured_even_when_notification_keeps_failing(
    _wire_firestore, seed_user, monkeypatch
):
    """The whole point of reschedule-first: even though notification fails
    on every attempt (and the job eventually gives up), the next escalation
    cycle was already secured on the very first attempt and stays that way
    (idempotent re-writes on each retry, not lost)."""
    _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
    seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

    monkeypatch.setattr(
        escalate_module, "_notify_management",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    escalate_down_time(NS, _payload(), "job-reschedule-survives")

    issue = _issue(_wire_firestore)
    assert issue["escalation_task_id"] == "issue-1-1"


def test_resolved_status_notification_failure_also_propagates_and_retries(
    _wire_firestore, seed_user, monkeypatch
):
    """Same proof as the pending/ongoing case, but for the `resolved` branch
    (`_notify_production_agents_awaiting_confirmation`) — both notification
    paths lost their containment, not just one."""
    _seed_issue(
        _wire_firestore, status=DownTimeStatus.RESOLVED.value,
        resolved_at=datetime.now().isoformat(),
    )
    seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value, push_token="tok")

    calls = {"n": 0}

    def _always_fails(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("simulated notification failure")

    monkeypatch.setattr(
        escalate_module, "_notify_production_agents_awaiting_confirmation", _always_fails
    )

    escalate_down_time(NS, _payload(), "job-resolved-notify-retried")

    assert calls["n"] == 3


def test_giveup_logs_error_after_exhausting_retries(
    _wire_firestore, seed_user, monkeypatch
):
    _seed_issue(_wire_firestore, status=DownTimeStatus.PENDING.value)
    seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok")

    monkeypatch.setattr(
        escalate_module, "_notify_management",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    logged = []
    monkeypatch.setattr(
        escalate_module.logger, "error", lambda msg: logged.append(msg)
    )

    escalate_down_time(NS, _payload(), "job-giveup-logged")

    assert any("gave up after" in msg for msg in logged)


def test_unexpected_status_stops_without_rescheduling(
    _wire_firestore, push_spy, email_spy, reschedule_spy
):
    _seed_issue(_wire_firestore, status="some-unexpected-status")

    result = escalate_down_time(NS, _payload(), "job-unexpected-status")

    assert result["status"] == "stopped"
    assert reschedule_spy == []
    assert push_spy == []
    assert len(email_spy) == 0


def test_missing_down_time_id_is_a_functional_error():
    result = escalate_down_time(NS, {}, "job-missing-id")
    assert result["status"] == "skipped"


def test_unknown_namespace_is_a_functional_error():
    result = escalate_down_time("no-such-ns", _payload(), "job-unknown-ns")
    assert result["status"] == "skipped"
