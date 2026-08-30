"""Tests for the `notify_down_time_update` async handler: recipients per
lifecycle event, self-skip rules, bilingual copy, tenant isolation, and the
functional-failure (unknown issue) path."""

import importlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.app.core.push import PushDeliveryError
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeStatus, ProductionScope, Process, Role

notify_module = importlib.import_module("src.app.async_jobs.notify_down_time_update")
notify_down_time_update = notify_module.notify_down_time_update

NS = "ns-notify-handler"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS)


@pytest.fixture(autouse=True)
def _wire_firestore(fake_db, monkeypatch):
    """`notify_down_time_update` holds its own imported reference to
    `get_firestore_client` — patch it directly against the same `fake_db` the
    `fake_db` fixture already wires everything else to."""
    client = FirestoreClient(client=fake_db)
    monkeypatch.setattr(notify_module, "get_firestore_client", lambda: client)
    return client


@pytest.fixture
def push_spy(monkeypatch):
    calls: list[dict] = []

    def _spy(tokens, title, body, data=None, notif_level="urgent"):
        calls.append(
            {
                "tokens": list(tokens),
                "title": title,
                "body": body,
                "data": data,
                "notif_level": notif_level,
            }
        )

    monkeypatch.setattr(notify_module, "send_push_notifications", _spy)
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
        "status": DownTimeStatus.ONGOING.value,
        "created_by": "creator-1",
    }
    issue.update(overrides)
    _wire_firestore.create_subdocument(
        "down_time", namespace_id, "issues", issue, document_id=down_time_id
    )
    return issue


def _payload(**overrides):
    base = {"down_time_id": "issue-1", "event": "acknowledged", "actor_id": "actor-1"}
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# acknowledged / resolved
# --------------------------------------------------------------------------- #


class TestAcknowledgedAndResolved:
    def test_acknowledged_notifies_creator(self, _wire_firestore, seed_user, push_spy):
        _seed_issue(_wire_firestore, created_by="creator-1")
        seed_user(id="creator-1", namespace_id=NS, push_token="tok-creator")

        result = notify_down_time_update(NS, _payload(event="acknowledged"), "job-1")

        assert result == {"status": "notified", "down_time_id": "issue-1", "event": "acknowledged"}
        assert len(push_spy) == 1
        assert push_spy[0]["tokens"] == ["tok-creator"]
        assert push_spy[0]["title"] == "Ticket acknowledged"

    def test_resolved_notifies_creator_with_resolve_copy(
        self, _wire_firestore, seed_user, push_spy
    ):
        _seed_issue(_wire_firestore, created_by="creator-1")
        seed_user(id="creator-1", namespace_id=NS, push_token="tok-creator")

        notify_down_time_update(NS, _payload(event="resolved"), "job-2")

        assert len(push_spy) == 1
        assert push_spy[0]["title"] == "Ticket resolved"
        assert "close the ticket" in push_spy[0]["body"]

    def test_actor_is_creator_is_never_notified_about_own_action(
        self, _wire_firestore, seed_user, push_spy
    ):
        _seed_issue(_wire_firestore, created_by="creator-1")
        seed_user(id="creator-1", namespace_id=NS, push_token="tok-creator")

        notify_down_time_update(
            NS, _payload(event="acknowledged", actor_id="creator-1"), "job-3"
        )

        assert push_spy == []

    def test_creator_without_push_token_is_a_silent_no_op(
        self, _wire_firestore, seed_user, push_spy
    ):
        _seed_issue(_wire_firestore, created_by="creator-1")
        seed_user(id="creator-1", namespace_id=NS, push_token=None)

        result = notify_down_time_update(NS, _payload(event="acknowledged"), "job-4")

        assert result["status"] == "notified"
        assert push_spy == []


# --------------------------------------------------------------------------- #
# rejected
# --------------------------------------------------------------------------- #


class TestRejected:
    def test_rejected_notifies_resolver_and_online_process_agents(
        self, _wire_firestore, seed_user, push_spy
    ):
        _seed_issue(_wire_firestore, created_by="creator-1", process=Process.MAINTENANCE.value)
        seed_user(
            id="resolver-1", namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            push_token="tok-resolver",
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok-agent",
        )

        result = notify_down_time_update(
            NS,
            _payload(event="rejected", rejected_resolver_id="resolver-1"),
            "job-5",
        )

        assert result == {"status": "notified", "down_time_id": "issue-1", "event": "rejected"}
        assert len(push_spy) == 2
        recipient_tokens = [set(c["tokens"]) for c in push_spy]
        assert {"tok-resolver"} in recipient_tokens
        assert {"tok-agent"} in recipient_tokens

        resolver_call = next(c for c in push_spy if "tok-resolver" in c["tokens"])
        assert resolver_call["title"] == "Resolution rejected"

    def test_resolver_is_actor_is_never_notified_about_own_action(
        self, _wire_firestore, seed_user, push_spy
    ):
        _seed_issue(_wire_firestore, created_by="creator-1", process=Process.MAINTENANCE.value)
        seed_user(
            id="resolver-1", namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            push_token="tok-resolver",
        )

        notify_down_time_update(
            NS,
            _payload(
                event="rejected", actor_id="resolver-1", rejected_resolver_id="resolver-1"
            ),
            "job-6",
        )

        assert all("tok-resolver" not in c["tokens"] for c in push_spy)

    def test_offline_or_tokenless_agents_are_never_notified(
        self, _wire_firestore, seed_user, push_spy
    ):
        _seed_issue(_wire_firestore, created_by="creator-1", process=Process.MAINTENANCE.value)
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=False, push_token="tok-offline",
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token=None,
        )

        notify_down_time_update(NS, _payload(event="rejected"), "job-7")

        assert push_spy == []

    def test_rejecting_agent_is_never_notified_about_own_rejection(
        self, _wire_firestore, seed_user, push_spy
    ):
        # Reachable path: ABSENTEEISM (not close-only) routes to
        # Process.PRODUCTION, so a production agent can acknowledge, resolve,
        # AND reject a resolution on the same ticket. The rejecting agent's
        # own device must never buzz about the rejection they just performed.
        _seed_issue(
            _wire_firestore,
            created_by="creator-1",
            process=Process.PRODUCTION.value,
            down_time_type="absenteeism",
        )
        seed_user(
            id="agent-actor", namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            online=True, push_token="tok-actor",
        )
        seed_user(
            namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            online=True, push_token="tok-other-agent",
        )

        notify_down_time_update(
            NS, _payload(event="rejected", actor_id="agent-actor"), "job-w1a"
        )

        all_tokens = {t for c in push_spy for t in c["tokens"]}
        assert "tok-actor" not in all_tokens
        assert "tok-other-agent" in all_tokens

    def test_resolver_who_is_also_a_process_agent_gets_exactly_one_push(
        self, _wire_firestore, seed_user, push_spy
    ):
        _seed_issue(_wire_firestore, created_by="creator-1", process=Process.MAINTENANCE.value)
        seed_user(
            id="resolver-1", namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok-resolver",
        )

        notify_down_time_update(
            NS,
            _payload(event="rejected", rejected_resolver_id="resolver-1"),
            "job-w1b",
        )

        calls_reaching_resolver = [c for c in push_spy if "tok-resolver" in c["tokens"]]
        assert len(calls_reaching_resolver) == 1
        assert calls_reaching_resolver[0]["title"] == "Resolution rejected"

    def test_agents_notification_states_time_open_since_created_at(
        self, _wire_firestore, seed_user, push_spy
    ):
        created_at = (datetime.now(ZoneInfo("UTC")) - timedelta(hours=3)).isoformat()
        _seed_issue(
            _wire_firestore,
            created_by="creator-1",
            process=Process.MAINTENANCE.value,
            created_at=created_at,
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok-agent",
        )

        notify_down_time_update(NS, _payload(event="rejected"), "job-8")

        agent_call = next(c for c in push_spy if "tok-agent" in c["tokens"])
        assert agent_call["title"] == "Downtime still unresolved"
        assert "3h" in agent_call["body"]

    def test_agents_notification_falls_back_gracefully_when_created_at_unparsable(
        self, _wire_firestore, seed_user, push_spy
    ):
        _seed_issue(
            _wire_firestore,
            created_by="creator-1",
            process=Process.MAINTENANCE.value,
            created_at="not-a-date",
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok-agent",
        )

        result = notify_down_time_update(NS, _payload(event="rejected"), "job-9")

        assert result["status"] == "notified"
        agent_call = next(c for c in push_spy if "tok-agent" in c["tokens"])
        assert "None" not in agent_call["body"]


# --------------------------------------------------------------------------- #
# Bilingual copy
# --------------------------------------------------------------------------- #


class TestLanguage:
    def test_french_namespace_produces_french_copy(
        self, seed_namespace, _wire_firestore, seed_user, push_spy
    ):
        seed_namespace(id=NS, language="fr")
        _seed_issue(_wire_firestore, created_by="creator-1")
        seed_user(id="creator-1", namespace_id=NS, push_token="tok-creator")

        notify_down_time_update(NS, _payload(event="acknowledged"), "job-10")

        assert push_spy[0]["title"] == "Ticket pris en charge"


# --------------------------------------------------------------------------- #
# Tenant isolation
# --------------------------------------------------------------------------- #


class TestTenantIsolation:
    def test_issue_from_another_namespace_is_never_touched(
        self, seed_namespace, _wire_firestore, seed_user, push_spy
    ):
        seed_namespace(id="other-ns")
        _seed_issue(_wire_firestore, namespace_id="other-ns", created_by="creator-1")
        seed_user(id="creator-1", namespace_id="other-ns", push_token="tok-creator")

        result = notify_down_time_update(NS, _payload(event="acknowledged"), "job-11")

        assert result["status"] == "skipped"
        assert push_spy == []

    def test_created_by_user_in_another_namespace_is_never_notified(
        self, seed_namespace, _wire_firestore, seed_user, push_spy
    ):
        # A forged/stale job message could pair this tenant's namespace_id
        # with a `created_by` id that happens to exist in another tenant.
        seed_namespace(id="other-ns")
        _seed_issue(_wire_firestore, created_by="victim-user")
        seed_user(id="victim-user", namespace_id="other-ns", push_token="tok-victim")

        notify_down_time_update(NS, _payload(event="acknowledged"), "job-12")

        assert push_spy == []


# --------------------------------------------------------------------------- #
# Functional failures — acked, never retried
# --------------------------------------------------------------------------- #


class TestFunctionalFailures:
    def test_unknown_issue_id_is_acked_as_functional_failure(self, push_spy):
        result = notify_down_time_update(
            NS, _payload(down_time_id="does-not-exist"), "job-13"
        )

        assert result["status"] == "skipped"
        assert push_spy == []

    def test_unknown_namespace_is_acked_as_functional_failure(self, push_spy):
        result = notify_down_time_update(
            "unknown-ns", _payload(), "job-14"
        )
        assert result["status"] == "skipped"
        assert push_spy == []

    def test_invalid_event_is_acked_as_functional_failure(
        self, _wire_firestore, push_spy
    ):
        _seed_issue(_wire_firestore)
        result = notify_down_time_update(NS, _payload(event="bogus"), "job-15")
        assert result["status"] == "skipped"
        assert push_spy == []

    def test_missing_actor_id_is_acked_as_functional_failure(
        self, _wire_firestore, push_spy
    ):
        _seed_issue(_wire_firestore)
        result = notify_down_time_update(NS, _payload(actor_id=None), "job-16")
        assert result["status"] == "skipped"
        assert push_spy == []


# --------------------------------------------------------------------------- #
# Redelivery is harmless (no state change, same message)
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Delivery-failure retry model (propagate to backoff) + the notify_user flag
# --------------------------------------------------------------------------- #


def _raising_spy(monkeypatch, fail_tokens):
    """Install a `send_push_notifications` spy that records every call and
    mimics the real contract: it raises `PushDeliveryError` when EVERY token
    in the (non-empty) batch is in `fail_tokens`, and returns otherwise. The
    `_no_real_backoff_sleep` autouse fixture keeps the retries instant."""
    calls: list[dict] = []

    def _spy(tokens, title, body, data=None, notif_level="urgent"):
        calls.append(
            {
                "tokens": list(tokens),
                "title": title,
                "body": body,
                "data": data,
                "notif_level": notif_level,
            }
        )
        valid = [t for t in tokens if t]
        if valid and all(t in fail_tokens for t in valid):
            raise PushDeliveryError("simulated total delivery failure")

    monkeypatch.setattr(notify_module, "send_push_notifications", _spy)
    return calls


class TestDeliveryFailureRetries:
    def test_user_push_failure_propagates_and_retries_three_times(
        self, _wire_firestore, seed_user, monkeypatch
    ):
        """A genuine delivery failure to the single addressed user must reach
        `backoff` and retry the whole run `max_tries` (3) times — no longer
        swallowed. `raise_on_giveup=False` means it still doesn't raise out."""
        _seed_issue(_wire_firestore, created_by="creator-1")
        seed_user(id="creator-1", namespace_id=NS, push_token="tok-creator")
        calls = _raising_spy(monkeypatch, fail_tokens={"tok-creator"})

        result = notify_down_time_update(NS, _payload(event="acknowledged"), "job-r1")

        # 3 attempts, every one re-pushing the (still-failing) creator.
        assert len(calls) == 3
        assert all(c["tokens"] == ["tok-creator"] for c in calls)
        assert result is None  # gave up (raise_on_giveup=False) -> acks

    def test_total_agent_failure_propagates_and_retries_three_times(
        self, _wire_firestore, seed_user, monkeypatch
    ):
        """Rejected with no resolver to notify: the process-agent fan-out is
        the only work, and a total agent outage propagates and retries."""
        _seed_issue(_wire_firestore, process=Process.MAINTENANCE.value)
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok-agent",
        )
        calls = _raising_spy(monkeypatch, fail_tokens={"tok-agent"})

        notify_down_time_update(NS, _payload(event="rejected"), "job-r2")

        assert len(calls) == 3
        assert all("tok-agent" in c["tokens"] for c in calls)

    def test_notify_user_flag_stops_the_user_being_re_pushed_on_agent_retries(
        self, _wire_firestore, seed_user, monkeypatch
    ):
        """The core of the requirement: once the addressed user (the rejected
        resolver) is reached, `notify_user` flips False, so the retries driven
        by a still-failing process-agent fan-out re-push ONLY the agents — the
        resolver is pushed exactly once across all 3 attempts."""
        _seed_issue(_wire_firestore, process=Process.MAINTENANCE.value)
        seed_user(
            id="resolver-1", namespace_id=NS, role=Role.PRODUCTION_AGENT.value,
            push_token="tok-resolver",
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok-agent",
        )
        # Only the agent fan-out fails; the resolver push succeeds.
        calls = _raising_spy(monkeypatch, fail_tokens={"tok-agent"})

        notify_down_time_update(
            NS,
            _payload(event="rejected", rejected_resolver_id="resolver-1"),
            "job-r3",
        )

        resolver_calls = [c for c in calls if "tok-resolver" in c["tokens"]]
        agent_calls = [c for c in calls if "tok-agent" in c["tokens"]]
        assert len(resolver_calls) == 1  # notified once, never re-pushed
        assert len(agent_calls) == 3     # retried until giveup


def test_redelivery_resends_but_causes_no_state_change(
    _wire_firestore, seed_user, push_spy
):
    _seed_issue(_wire_firestore, created_by="creator-1")
    seed_user(id="creator-1", namespace_id=NS, push_token="tok-creator")

    first = notify_down_time_update(NS, _payload(event="acknowledged"), "job-17")
    second = notify_down_time_update(NS, _payload(event="acknowledged"), "job-17")

    assert first == second
    # Best-effort at-least-once delivery: a replay resends (no Firestore
    # write to short-circuit against), but it's the exact same message.
    assert len(push_spy) == 2
    assert push_spy[0] == push_spy[1]
