"""Direct unit-style tests for the `add_down_time` async handler:
idempotency and namespace-timezone resolution (things the endpoint tests can't
easily assert through HTTP)."""

import importlib
from datetime import datetime, timedelta

import pytest

from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeType, ProductionScope, Role

add_down_time_module = importlib.import_module("src.app.async_jobs.add_down_time")
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
        calls.append({"tokens": list(tokens), "data": data})

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
