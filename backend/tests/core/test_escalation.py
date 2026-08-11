"""Tests for `src.app.core.escalation`.

`should_escalate` is a pure predicate — no mocking needed. The scheduling
helpers (`schedule_escalation`, `cancel_escalation`) are best-effort wrappers
around `get_cloud_task_manager()`; `create_task`'s own UTC-default fallback
for a missing/blank `timezone_name` is covered directly on `CloudTask`
(mocked GCP client — never touches real GCP).

`schedule_escalation` returns a `ScheduleEscalationResult(task_id,
already_existed)`, not a bare id — `AlreadyExists` is ambiguous (already
scheduled vs. a tombstoned name) and must be reported distinctly, never
folded into a plain success return. `CloudTask.create_task` itself no
longer swallows `AlreadyExists` at all — it propagates, and `schedule_escalation`
is the layer that catches and classifies it.
"""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from google.api_core import exceptions as gcp_exceptions

from src.app.core.escalation import (
    ESCALATION_DELAY_SECONDS,
    ScheduleEscalationResult,
    cancel_escalation,
    schedule_escalation,
    should_escalate,
)
from src.app.gcp.cloud_tasks import CloudTask
from src.app.globals.enum import JobType, ProductionScope, WorkstationType


@pytest.fixture
def cloud_task():
    """A `CloudTask` instance with a mocked GCP client — bypasses
    `__init__`'s queue creation/lookup so no real GCP call is made."""
    instance = CloudTask.__new__(CloudTask)
    instance.client = MagicMock()
    instance.location = "europe-west1"
    instance.queue_path = "projects/p/locations/europe-west1/queues/q"
    return instance


class TestShouldEscalatePlantUapProductionLine:
    def test_plant_scope_always_escalates(self):
        issue = {"down_time_scope": ProductionScope.PLANT.value}
        assert should_escalate(issue, None) is True

    def test_uap_scope_always_escalates(self):
        issue = {"down_time_scope": ProductionScope.UAP.value}
        assert should_escalate(issue, None) is True

    def test_production_line_scope_always_escalates(self):
        issue = {"down_time_scope": ProductionScope.PRODUCTION_LINE.value}
        assert should_escalate(issue, None) is True

    def test_area_scopes_escalate_regardless_of_workstation(self):
        issue = {"down_time_scope": ProductionScope.PLANT.value}
        workstation = {"type": WorkstationType.STANDARD.value}
        assert should_escalate(issue, workstation) is True


class TestShouldEscalateWorkStation:
    def test_bottleneck_workstation_escalates(self):
        issue = {"down_time_scope": ProductionScope.WORK_STATION.value}
        workstation = {"type": WorkstationType.BOTTLENECK.value}
        assert should_escalate(issue, workstation) is True

    def test_critical_workstation_escalates(self):
        issue = {"down_time_scope": ProductionScope.WORK_STATION.value}
        workstation = {"type": WorkstationType.CRITICAL.value}
        assert should_escalate(issue, workstation) is True

    def test_standard_workstation_does_not_escalate(self):
        issue = {"down_time_scope": ProductionScope.WORK_STATION.value}
        workstation = {"type": WorkstationType.STANDARD.value}
        assert should_escalate(issue, workstation) is False

    def test_missing_workstation_document_does_not_escalate(self):
        issue = {"down_time_scope": ProductionScope.WORK_STATION.value}
        assert should_escalate(issue, None) is False

    def test_missing_type_field_does_not_escalate(self):
        issue = {"down_time_scope": ProductionScope.WORK_STATION.value}
        workstation = {}
        assert should_escalate(issue, workstation) is False

    def test_unknown_type_value_does_not_escalate(self):
        issue = {"down_time_scope": ProductionScope.WORK_STATION.value}
        workstation = {"type": "some_unknown_type"}
        assert should_escalate(issue, workstation) is False


class TestScheduleEscalation:
    @patch("src.app.core.escalation.get_cloud_task_manager")
    def test_returns_created_task_id(self, mock_get_manager):
        mock_manager = MagicMock()
        mock_manager.create_task.return_value = "task-123"
        mock_get_manager.return_value = mock_manager

        result = schedule_escalation("ns-1", "down-time-1", "Europe/Paris")

        assert result == ScheduleEscalationResult(task_id="task-123", already_existed=False)
        mock_manager.create_task.assert_called_once_with(
            delay=ESCALATION_DELAY_SECONDS,
            namespace_id="ns-1",
            job_type=JobType.ESCALATE_DOWN_TIME,
            timezone_name="Europe/Paris",
            payload={"down_time_id": "down-time-1"},
            task_id=None,
        )

    @patch("src.app.core.escalation.get_cloud_task_manager")
    def test_forwards_explicit_task_id(self, mock_get_manager):
        mock_manager = MagicMock()
        mock_manager.create_task.return_value = "task-abc"
        mock_get_manager.return_value = mock_manager

        result = schedule_escalation(
            "ns-1", "down-time-1", "Europe/Paris", task_id="task-abc"
        )

        assert result == ScheduleEscalationResult(task_id="task-abc", already_existed=False)
        mock_manager.create_task.assert_called_once_with(
            delay=ESCALATION_DELAY_SECONDS,
            namespace_id="ns-1",
            job_type=JobType.ESCALATE_DOWN_TIME,
            timezone_name="Europe/Paris",
            payload={"down_time_id": "down-time-1"},
            task_id="task-abc",
        )

    @patch("src.app.core.escalation.get_cloud_task_manager")
    def test_escalation_number_included_in_payload_when_given(self, mock_get_manager):
        mock_manager = MagicMock()
        mock_manager.create_task.return_value = "down-time-1-3"
        mock_get_manager.return_value = mock_manager

        result = schedule_escalation(
            "ns-1", "down-time-1", None, task_id="down-time-1-3", escalation_number=3
        )

        assert result == ScheduleEscalationResult(
            task_id="down-time-1-3", already_existed=False
        )
        mock_manager.create_task.assert_called_once_with(
            delay=ESCALATION_DELAY_SECONDS,
            namespace_id="ns-1",
            job_type=JobType.ESCALATE_DOWN_TIME,
            timezone_name=None,
            payload={"down_time_id": "down-time-1", "escalation_number": 3},
            task_id="down-time-1-3",
        )

    @patch("src.app.core.escalation.get_cloud_task_manager")
    def test_escalation_number_omitted_from_payload_when_not_given(self, mock_get_manager):
        mock_manager = MagicMock()
        mock_manager.create_task.return_value = "task-123"
        mock_get_manager.return_value = mock_manager

        schedule_escalation("ns-1", "down-time-1", None)

        _, kwargs = mock_manager.create_task.call_args
        assert kwargs["payload"] == {"down_time_id": "down-time-1"}
        assert "escalation_number" not in kwargs["payload"]

    @patch("src.app.core.escalation.get_cloud_task_manager")
    def test_swallows_exception_and_returns_none_task_id(self, mock_get_manager):
        mock_manager = MagicMock()
        mock_manager.create_task.side_effect = RuntimeError("Cloud Tasks outage")
        mock_get_manager.return_value = mock_manager

        result = schedule_escalation("ns-1", "down-time-1", None)

        assert result == ScheduleEscalationResult(task_id=None, already_existed=False)

    @patch("src.app.core.escalation.get_cloud_task_manager")
    def test_forwards_task_id_and_still_returns_none_on_other_failure(
        self, mock_get_manager
    ):
        mock_manager = MagicMock()
        mock_manager.create_task.side_effect = RuntimeError("Cloud Tasks outage")
        mock_get_manager.return_value = mock_manager

        result = schedule_escalation(
            "ns-1", "down-time-1", None, task_id="task-retry-1"
        )

        assert result == ScheduleEscalationResult(task_id=None, already_existed=False)
        mock_manager.create_task.assert_called_once_with(
            delay=ESCALATION_DELAY_SECONDS,
            namespace_id="ns-1",
            job_type=JobType.ESCALATE_DOWN_TIME,
            timezone_name=None,
            payload={"down_time_id": "down-time-1"},
            task_id="task-retry-1",
        )

    @patch("src.app.core.escalation.get_cloud_task_manager")
    def test_swallows_manager_lookup_exception(self, mock_get_manager):
        mock_get_manager.side_effect = RuntimeError("no project id configured")

        result = schedule_escalation("ns-1", "down-time-1", "UTC")

        assert result == ScheduleEscalationResult(task_id=None, already_existed=False)

    @patch("src.app.core.escalation.get_cloud_task_manager")
    def test_already_exists_reports_already_existed_true_with_the_task_id(
        self, mock_get_manager
    ):
        mock_manager = MagicMock()
        mock_manager.create_task.side_effect = gcp_exceptions.AlreadyExists(
            "task already exists"
        )
        mock_get_manager.return_value = mock_manager

        result = schedule_escalation(
            "ns-1", "down-time-1", None, task_id="down-time-1-2"
        )

        assert result == ScheduleEscalationResult(
            task_id="down-time-1-2", already_existed=True
        )

    @patch("src.app.core.escalation.get_cloud_task_manager")
    def test_already_exists_never_raises(self, mock_get_manager):
        mock_manager = MagicMock()
        mock_manager.create_task.side_effect = gcp_exceptions.AlreadyExists(
            "task already exists"
        )
        mock_get_manager.return_value = mock_manager

        # Must not raise — `AlreadyExists` is an expected, classified outcome.
        schedule_escalation("ns-1", "down-time-1", None, task_id="down-time-1-2")

    def test_unconfigured_project_id_logs_below_error_with_configured_message(
        self, monkeypatch
    ):
        """`get_cloud_task_manager` -> `CloudTask.__init__` ->
        `_create_queue_path` raises `ValueError` when `google_project_id`
        isn't set — the ordinary state of an unconfigured environment, not a
        genuine scheduling failure. Must log at warning (or below), never
        error, with a message that says the feature isn't configured."""
        import src.app.core.escalation as escalation_module

        def _raise_unconfigured(*args, **kwargs):
            raise ValueError("Google Project ID is not set.")

        monkeypatch.setattr(
            escalation_module, "get_cloud_task_manager", _raise_unconfigured
        )

        logged_errors = []
        logged_warnings = []
        monkeypatch.setattr(
            escalation_module.logger, "error", lambda msg, *a, **k: logged_errors.append(msg)
        )
        monkeypatch.setattr(
            escalation_module.logger, "warning", lambda msg, *a, **k: logged_warnings.append(msg)
        )

        result = schedule_escalation("ns-1", "down-time-1", None, task_id="down-time-1-1")

        assert result == ScheduleEscalationResult(task_id=None, already_existed=False)
        assert logged_errors == []
        assert len(logged_warnings) == 1
        assert "not configured" in logged_warnings[0].lower()


class TestCancelEscalation:
    def test_falsy_task_id_is_a_noop(self):
        assert cancel_escalation(None) is False
        assert cancel_escalation("") is False

    @patch("src.app.core.escalation.get_cloud_task_manager")
    def test_delegates_to_delete_task(self, mock_get_manager):
        mock_manager = MagicMock()
        mock_manager.delete_task.return_value = True
        mock_get_manager.return_value = mock_manager

        assert cancel_escalation("task-123") is True
        mock_manager.delete_task.assert_called_once_with("task-123")

    @patch("src.app.core.escalation.get_cloud_task_manager")
    def test_swallows_exception_and_returns_false(self, mock_get_manager):
        mock_manager = MagicMock()
        mock_manager.delete_task.side_effect = RuntimeError("Cloud Tasks outage")
        mock_get_manager.return_value = mock_manager

        assert cancel_escalation("task-123") is False


class TestCreateTaskTimezoneDefault:
    """`CloudTask.create_task` must tolerate a missing/blank `timezone_name`
    (legacy namespace documents predate the `timezone` field), defaulting to
    UTC exactly like `core.timezone.namespace_timezone`."""

    def test_none_timezone_name_defaults_to_utc(self, cloud_task):
        with patch("src.app.gcp.cloud_tasks.ZoneInfo") as mock_zoneinfo:
            mock_zoneinfo.return_value = ZoneInfo("UTC")
            task_id = cloud_task.create_task(
                delay=60,
                namespace_id="ns-1",
                job_type=JobType.ESCALATE_DOWN_TIME,
                timezone_name=None,
            )

        assert task_id
        cloud_task.client.create_task.assert_called_once()
        mock_zoneinfo.assert_called_once_with("UTC")

    def test_blank_timezone_name_defaults_to_utc(self, cloud_task):
        with patch("src.app.gcp.cloud_tasks.ZoneInfo") as mock_zoneinfo:
            mock_zoneinfo.return_value = ZoneInfo("UTC")
            task_id = cloud_task.create_task(
                delay=60,
                namespace_id="ns-1",
                job_type=JobType.ESCALATE_DOWN_TIME,
                timezone_name="",
            )

        assert task_id
        mock_zoneinfo.assert_called_once_with("UTC")

    def test_valid_timezone_name_still_used(self, cloud_task):
        task_id = cloud_task.create_task(
            delay=60,
            namespace_id="ns-1",
            job_type=JobType.ESCALATE_DOWN_TIME,
            timezone_name="Europe/Paris",
        )

        assert task_id
        _, kwargs = cloud_task.client.create_task.call_args
        schedule_time = kwargs["request"]["task"].schedule_time
        # Proto Timestamp collapses to an absolute UTC instant, so assert
        # via the source ZoneInfo instead of the resulting offset.
        expected = datetime.now(ZoneInfo("Europe/Paris")) + timedelta(seconds=60)
        assert abs((schedule_time - expected).total_seconds()) < 5

    def test_payload_merged_under_payload_key(self, cloud_task):
        cloud_task.create_task(
            delay=60,
            namespace_id="ns-1",
            job_type=JobType.ESCALATE_DOWN_TIME,
            timezone_name=None,
            payload={"down_time_id": "dt-1"},
        )

        _, kwargs = cloud_task.client.create_task.call_args
        body = json.loads(kwargs["request"]["task"].http_request.body)
        assert body["payload"] == {"down_time_id": "dt-1"}


class TestCreateTaskIdempotency:
    """`create_task(task_id=...)` makes creation safe to retry: the same
    explicit id is reused as the task name. `AlreadyExists` is no longer
    swallowed here (see `TestScheduleEscalation` for the layer that
    classifies it) — this class just proves the id is used as the task name
    and that `AlreadyExists` propagates unmodified."""

    def test_explicit_task_id_used_as_task_name(self, cloud_task):
        result = cloud_task.create_task(
            delay=60,
            namespace_id="ns-1",
            job_type=JobType.ESCALATE_DOWN_TIME,
            timezone_name=None,
            task_id="explicit-task-id",
        )

        assert result == "explicit-task-id"
        _, kwargs = cloud_task.client.create_task.call_args
        task = kwargs["request"]["task"]
        assert task.name == f"{cloud_task.queue_path}/tasks/explicit-task-id"

    def test_omitted_task_id_still_mints_uuid(self, cloud_task):
        result = cloud_task.create_task(
            delay=60,
            namespace_id="ns-1",
            job_type=JobType.ESCALATE_DOWN_TIME,
            timezone_name=None,
        )

        assert result
        # A UUID4 string, not any fixed/predictable value.
        uuid.UUID(result)

    def test_already_exists_propagates(self, cloud_task):
        cloud_task.client.create_task.side_effect = gcp_exceptions.AlreadyExists(
            "task already exists"
        )

        with pytest.raises(gcp_exceptions.AlreadyExists):
            cloud_task.create_task(
                delay=60,
                namespace_id="ns-1",
                job_type=JobType.ESCALATE_DOWN_TIME,
                timezone_name=None,
                task_id="explicit-task-id",
            )

    def test_other_gcp_error_still_propagates(self, cloud_task):
        cloud_task.client.create_task.side_effect = gcp_exceptions.PermissionDenied(
            "no permission"
        )

        with pytest.raises(gcp_exceptions.PermissionDenied):
            cloud_task.create_task(
                delay=60,
                namespace_id="ns-1",
                job_type=JobType.ESCALATE_DOWN_TIME,
                timezone_name=None,
                task_id="explicit-task-id",
            )
