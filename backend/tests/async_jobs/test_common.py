"""Direct unit tests for `_common.schedule_escalation_cycle` — the single
composition (deterministic task id + `schedule_escalation` call + issue
bookkeeping write) both `add_down_time` (cycle 1) and `escalate_down_time`
(cycle `n+1`) call, so its own contract is tested once, at the source,
rather than only indirectly through each handler.

Three distinct `schedule_escalation` outcomes, only one of which writes to
Firestore — see `schedule_escalation_cycle`'s docstring:
  * created (`already_existed=False`, `task_id` set) -> persists bookkeeping.
  * `already_existed=True` -> logged at info, NO write (redundant — whoever
    created it already wrote it; also avoids drifting `escalated_at`).
  * `task_id is None` (genuine failure) -> logged at error, NO write.
"""

import importlib
from datetime import datetime

import pytest

from src.app.core.escalation import ESCALATION_DELAY_SECONDS, ScheduleEscalationResult
from src.app.core.firestore import NAMESPACE_SETTINGS_COLLECTION, SETTINGS_SUBCOLLECTION
from src.app.gcp.firestore import FirestoreClient

common_module = importlib.import_module("src.app.async_jobs._common")
schedule_escalation_cycle = common_module.schedule_escalation_cycle
_resolve_escalation_delay = common_module._resolve_escalation_delay

NS = "ns-common-handler"
DOWN_TIME_ID = "issue-1"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS)


@pytest.fixture
def _wire(fake_db):
    return FirestoreClient(client=fake_db)


def _seed_issue(client, **overrides):
    issue = {
        "id": DOWN_TIME_ID,
        "namespace_id": NS,
        "created_at": datetime.now().isoformat(),
        "escalation_task_id": "old-task-id",
    }
    issue.update(overrides)
    client.create_subdocument(
        "down_time", NS, "issues", issue, document_id=DOWN_TIME_ID
    )
    return issue


def _issue(client):
    return client.get_subdocument("down_time", NS, "issues", DOWN_TIME_ID)


def _seed_settings(client, namespace_id=NS, **overrides):
    """Seed `NamespaceSettings/{namespace_id}/settings/{namespace_id}` directly
    — the exact document `_resolve_escalation_delay` reads."""
    data = {"id": namespace_id}
    data.update(overrides)
    client.create_subdocument(
        NAMESPACE_SETTINGS_COLLECTION, namespace_id, SETTINGS_SUBCOLLECTION,
        data, document_id=namespace_id,
    )
    return data


@pytest.fixture
def schedule_spy(monkeypatch):
    """Spy on the innermost `schedule_escalation` primitive
    `schedule_escalation_cycle` calls, reporting a clean "created" outcome
    (`already_existed=False`) by default."""
    calls: list[dict] = []

    def _spy(namespace_id, down_time_id, timezone_name, task_id=None, escalation_number=None, delay=None):
        calls.append(
            {
                "namespace_id": namespace_id,
                "down_time_id": down_time_id,
                "timezone_name": timezone_name,
                "task_id": task_id,
                "escalation_number": escalation_number,
                "delay": delay,
            }
        )
        return ScheduleEscalationResult(task_id=task_id, already_existed=False)

    monkeypatch.setattr(common_module, "schedule_escalation", _spy)
    return calls


class TestIdComposition:
    def test_task_id_composed_from_down_time_id_and_escalation_number(
        self, _wire, schedule_spy
    ):
        _seed_issue(_wire)

        result = schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 1)

        assert result == "issue-1-1"
        assert schedule_spy[0]["task_id"] == "issue-1-1"
        assert schedule_spy[0]["escalation_number"] == 1

    def test_escalation_number_forwarded_to_schedule_escalation(self, _wire, schedule_spy):
        _seed_issue(_wire)

        schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 7)

        assert schedule_spy[0]["task_id"] == "issue-1-7"
        assert schedule_spy[0]["escalation_number"] == 7

    def test_namespace_timezone_forwarded(self, _wire, schedule_spy):
        _seed_issue(_wire)

        schedule_escalation_cycle(
            _wire, NS, {"timezone": "Europe/Paris"}, DOWN_TIME_ID, 1
        )

        assert schedule_spy[0]["timezone_name"] == "Europe/Paris"

    def test_missing_namespace_defaults_timezone_to_none(self, _wire, schedule_spy):
        _seed_issue(_wire)

        schedule_escalation_cycle(_wire, NS, None, DOWN_TIME_ID, 1)

        assert schedule_spy[0]["timezone_name"] is None


class TestEscalationCountConvention:
    def test_cycle_one_persists_escalation_count_zero(self, _wire, schedule_spy):
        """`add_down_time` schedules cycle 1 -> no cycle has executed yet."""
        _seed_issue(_wire)

        schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 1)

        issue = _issue(_wire)
        assert issue["escalation_count"] == 0
        assert issue["escalation_task_id"] == "issue-1-1"
        assert "escalated_at" in issue and issue["escalated_at"]

    def test_cycle_n_plus_one_persists_escalation_count_n(self, _wire, schedule_spy):
        """`escalate_down_time` at incoming cycle `n` schedules `n+1` ->
        `escalation_count` lands at `n`, the cycle that just ran."""
        _seed_issue(_wire)

        schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 5)

        issue = _issue(_wire)
        assert issue["escalation_count"] == 4
        assert issue["escalation_task_id"] == "issue-1-5"


class TestGenuineFailureDoesNotWrite:
    def test_none_task_id_does_not_write_to_firestore(self, _wire, monkeypatch):
        _seed_issue(
            _wire, escalation_task_id="old-task-id", escalation_count=2,
            escalated_at="2020-01-01T00:00:00+00:00",
        )
        before = _issue(_wire)

        monkeypatch.setattr(
            common_module, "schedule_escalation",
            lambda *a, **k: ScheduleEscalationResult(task_id=None, already_existed=False),
        )

        result = schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 3)

        assert result is None
        after = _issue(_wire)
        assert after == before

    def test_none_task_id_logs_error_with_down_time_id(self, _wire, monkeypatch):
        _seed_issue(_wire)
        monkeypatch.setattr(
            common_module, "schedule_escalation",
            lambda *a, **k: ScheduleEscalationResult(task_id=None, already_existed=False),
        )

        logged = []
        monkeypatch.setattr(common_module.logger, "error", lambda msg: logged.append(msg))

        schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 3)

        assert any(DOWN_TIME_ID in msg for msg in logged)

    def test_success_returns_the_task_id(self, _wire, schedule_spy):
        _seed_issue(_wire)

        result = schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 1)

        assert result == "issue-1-1"


class TestAlreadyExistedDoesNotWrite:
    """`already_existed=True` must behave like the `None` case for write
    purposes (no Firestore write), but is logged at INFO, not error — it's
    a normal, healthy outcome, not a problem."""

    def test_already_existed_true_does_not_write_to_firestore(self, _wire, monkeypatch):
        _seed_issue(
            _wire, escalation_task_id="old-task-id", escalation_count=2,
            escalated_at="2020-01-01T00:00:00+00:00",
        )
        before = _issue(_wire)

        monkeypatch.setattr(
            common_module, "schedule_escalation",
            lambda *a, **k: ScheduleEscalationResult(
                task_id="issue-1-3", already_existed=True
            ),
        )

        result = schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 3)

        assert result == "issue-1-3"
        after = _issue(_wire)
        assert after == before

    def test_already_existed_true_still_returns_the_task_id(self, _wire, monkeypatch):
        _seed_issue(_wire)
        monkeypatch.setattr(
            common_module, "schedule_escalation",
            lambda *a, **k: ScheduleEscalationResult(
                task_id="issue-1-1", already_existed=True
            ),
        )

        result = schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 1)

        assert result == "issue-1-1"

    def test_already_existed_true_logs_at_info_not_error(self, _wire, monkeypatch):
        _seed_issue(_wire)
        monkeypatch.setattr(
            common_module, "schedule_escalation",
            lambda *a, **k: ScheduleEscalationResult(
                task_id="issue-1-1", already_existed=True
            ),
        )

        logged_errors = []
        logged_infos = []
        monkeypatch.setattr(
            common_module.logger, "error", lambda msg: logged_errors.append(msg)
        )
        monkeypatch.setattr(
            common_module.logger, "info", lambda msg: logged_infos.append(msg)
        )

        schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 1)

        assert logged_errors == []
        assert any(DOWN_TIME_ID in msg for msg in logged_infos)


# --------------------------------------------------------------------------- #
# `_resolve_escalation_delay` — namespace-configured escalation delay
# --------------------------------------------------------------------------- #


class TestResolveEscalationDelay:
    def test_returns_configured_delay_when_settings_exist(self, _wire):
        _seed_settings(_wire, time_to_escalate=600)

        assert _resolve_escalation_delay(_wire, NS) == 600

    def test_defaults_when_no_settings_doc_exists(self, _wire):
        assert _resolve_escalation_delay(_wire, NS) == ESCALATION_DELAY_SECONDS

    def test_defaults_when_field_missing(self, _wire):
        _seed_settings(_wire)

        assert _resolve_escalation_delay(_wire, NS) == ESCALATION_DELAY_SECONDS

    def test_defaults_when_field_is_none(self, _wire):
        _seed_settings(_wire, time_to_escalate=None)

        assert _resolve_escalation_delay(_wire, NS) == ESCALATION_DELAY_SECONDS

    def test_defaults_when_field_is_zero(self, _wire):
        _seed_settings(_wire, time_to_escalate=0)

        assert _resolve_escalation_delay(_wire, NS) == ESCALATION_DELAY_SECONDS

    def test_defaults_when_field_is_negative(self, _wire):
        _seed_settings(_wire, time_to_escalate=-100)

        assert _resolve_escalation_delay(_wire, NS) == ESCALATION_DELAY_SECONDS

    def test_defaults_when_field_is_wrong_type(self, _wire):
        _seed_settings(_wire, time_to_escalate="600")

        assert _resolve_escalation_delay(_wire, NS) == ESCALATION_DELAY_SECONDS


# --------------------------------------------------------------------------- #
# `schedule_escalation_cycle` forwards the resolved delay to
# `schedule_escalation`
# --------------------------------------------------------------------------- #


class TestScheduleEscalationCycleForwardsDelay:
    def test_custom_settings_delay_is_forwarded(self, _wire, schedule_spy):
        _seed_issue(_wire)
        _seed_settings(_wire, time_to_escalate=600)

        schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 1)

        assert schedule_spy[0]["delay"] == 600

    def test_default_delay_used_when_no_settings_doc(self, _wire, schedule_spy):
        _seed_issue(_wire)

        schedule_escalation_cycle(_wire, NS, {"timezone": None}, DOWN_TIME_ID, 1)

        assert schedule_spy[0]["delay"] == ESCALATION_DELAY_SECONDS
