"""API tests for `POST /pubsub_job` — the Pub/Sub push worker entrypoint.

Covers `.claude/specs/pubsub-worker-endpoint.md` §4 revision 2 (scenarios
1-12, post gate-review). The route does not exist yet (test-first gate):
every test here must fail either on its own assertion or on the missing
route (404), never on a broken fixture.

`/pubsub_job` receives the Pub/Sub push envelope (`{"message": {"data": ...
base64 JSON ..., "messageId": ..., ...}, "subscription": ...}`), decodes
`message.data` into the flat `{job_id, job_type, namespace_id, payload}`
shape `POST /cloud_job` already accepts — `job_type` is read from the
**root** of the decoded JSON, alongside `namespace_id`/`job_id`, exactly as
`publish_job` writes it — and delegates to the same `services.
process_cloud_job` engine, so the job registry is mocked exactly the way
`test_down_time.py::TestCloudJobWorker` exercises the real handlers, except
here we substitute a spy handler via `get_job_handler` so these tests assert
transformation/dispatch behavior, not a specific domain handler.

Revision 2 (dropped vs. revision 1, per developer/reviewer decision at the
gate — already handled downstream by the handler, not re-implemented here):
- no `job_id` fallback to `message.messageId` — `job_id` passes through
  as-is (`None` when absent);
- no dedicated scenario for a missing `namespace_id` in the decoded JSON —
  it falls into the same generic "cannot build CloudJobIn -> log + ack 200"
  branch as any other unconvertible envelope, with no special-casing.

Revision 2 also makes observability mandatory: every branch that acks
without running a job must `logger.error` (on `src.app.routers.workers.
services`) before returning, identifying what is known about the message
(job_type/job_id when known, or an identifying envelope field otherwise).
Each such test asserts that log via `caplog`, matching on a substring
robust to message rewording — never the exact string.

Every malformed envelope must still ack `200` (never 4xx/5xx) — a non-2xx
here makes Pub/Sub redeliver the message forever, and a message that can
never succeed must not be requeued (same rule as `/cloud_job`).

Scenario 12 (non-regression on `/cloud_job`) is exercised here, in a new
class, without touching `tests/api/test_down_time.py` — those tests must
stay green untouched.
"""

import base64
import importlib
import json
import logging

import pytest

workers_services_module = importlib.import_module("src.app.routers.workers.services")
WORKERS_SERVICES_LOGGER = "src.app.routers.workers.services"

PUBSUB_JOB_URL = "/pubsub_job"
CLOUD_JOB_URL = "/cloud_job"
KNOWN_JOB_TYPE = "add_down_time"
NS = "ns-pubsub"


def _b64(obj) -> str:
    """Base64-encode a JSON-serializable object the way `publish_job` encodes
    the Pub/Sub message body."""
    return base64.b64encode(json.dumps(obj).encode("utf-8")).decode("utf-8")


def _envelope(
    data=None,
    message_id="msg-1",
    subscription="projects/p/subscriptions/s",
    omit_message=False,
    omit_data=False,
):
    """Build a Pub/Sub push envelope. `data` is expected to already be a
    base64 string (or None to omit the field)."""
    message = {}
    if not omit_data:
        message["data"] = data
    message["messageId"] = message_id
    message["publishTime"] = "2026-08-28T10:00:00Z"
    message["attributes"] = {}

    envelope = {"subscription": subscription}
    if not omit_message:
        envelope["message"] = message
    return envelope


@pytest.fixture
def handler_spy(monkeypatch):
    """Replace the job registry lookup (`get_job_handler`, as bound into
    `src.app.routers.workers.services`) with a fake: only `KNOWN_JOB_TYPE`
    resolves to a handler, which records every call and returns a fixed
    result. Never touches the real `async_jobs` registry or runs a real
    domain handler."""
    calls: list[dict] = []

    def _fake_get_job_handler(job_type):
        if job_type != KNOWN_JOB_TYPE:
            return None

        def _handler(namespace_id, payload, job_id):
            calls.append(
                {"namespace_id": namespace_id, "payload": payload, "job_id": job_id}
            )
            return {"status": "handled"}

        return _handler

    monkeypatch.setattr(workers_services_module, "get_job_handler", _fake_get_job_handler)
    return calls


def _error_records(caplog):
    return [
        r
        for r in caplog.records
        if r.name == WORKERS_SERVICES_LOGGER and r.levelno == logging.ERROR
    ]


# --------------------------------------------------------------------------- #
# 1-3: valid envelope -> transformed and dispatched
# --------------------------------------------------------------------------- #


class TestPubSubJobDispatch:
    """POST /pubsub_job — valid push envelope is decoded and delegated to
    the same engine as /cloud_job. `job_type` is read from the root of the
    decoded JSON, alongside `namespace_id`/`job_id`."""

    def test_valid_envelope_dispatches_handler_and_returns_200(
        self, client, fake_db, handler_spy
    ):
        data = _b64(
            {
                "job_id": "job-1",
                "job_type": KNOWN_JOB_TYPE,
                "namespace_id": NS,
                "payload": {"foo": "bar"},
            }
        )
        res = client.post(PUBSUB_JOB_URL, json=_envelope(data=data, message_id="msg-1"))

        assert res.status_code == 200, res.text
        body = res.json()["data"]
        assert body["job_id"] == "job-1"
        assert body["result"] == {"status": "handled"}
        assert len(handler_spy) == 1
        assert handler_spy[0] == {
            "namespace_id": NS,
            "payload": {"foo": "bar"},
            "job_id": "job-1",
        }

    def test_missing_payload_defaults_to_empty_dict_and_logs_error(
        self, client, fake_db, handler_spy, caplog
    ):
        data = _b64(
            {
                "job_id": "job-no-payload",
                "job_type": KNOWN_JOB_TYPE,
                "namespace_id": NS,
            }
        )
        with caplog.at_level(logging.ERROR, logger=WORKERS_SERVICES_LOGGER):
            res = client.post(PUBSUB_JOB_URL, json=_envelope(data=data))

        assert res.status_code == 200, res.text
        assert len(handler_spy) == 1
        assert handler_spy[0]["payload"] == {}
        # The job still runs (with `{}`), but the absent payload is itself
        # logged as an error so a silently-dropped payload stays visible.
        errors = _error_records(caplog)
        assert len(errors) == 1
        assert "payload" in errors[0].getMessage().lower()

    def test_extra_publish_metadata_fields_are_ignored(
        self, client, fake_db, handler_spy
    ):
        data = _b64(
            {
                "job_id": "job-extra",
                "job_type": KNOWN_JOB_TYPE,
                "namespace_id": NS,
                "attempt": 3,
                "created_at": "2026-08-28T10:00:00+00:00",
                "payload": {"foo": "bar"},
            }
        )
        res = client.post(PUBSUB_JOB_URL, json=_envelope(data=data))

        assert res.status_code == 200, res.text
        assert len(handler_spy) == 1
        assert handler_spy[0]["job_id"] == "job-extra"
        assert handler_spy[0]["payload"] == {"foo": "bar"}


# --------------------------------------------------------------------------- #
# 4-10: malformed input never returns a non-200, and is always logged
# --------------------------------------------------------------------------- #


class TestPubSubJobMalformedEnvelopeAlwaysAcks200:
    """Every malformed input acks 200 without ever calling a handler, so
    Pub/Sub never redelivers a message that cannot succeed — and every such
    branch logs an ERROR (on `src.app.routers.workers.services`) before
    returning, so a dropped message stays visible. Each assertion matches a
    substring we control (a job_type/job_id we set, or an identifying
    envelope field), not the implementer's exact wording."""

    def test_unknown_job_type_acks_200_without_calling_handler_and_logs_error(
        self, client, fake_db, handler_spy, caplog
    ):
        data = _b64(
            {"job_id": "job-x", "job_type": "not_a_real_job", "namespace_id": NS}
        )
        with caplog.at_level(logging.ERROR, logger=WORKERS_SERVICES_LOGGER):
            res = client.post(PUBSUB_JOB_URL, json=_envelope(data=data))

        assert res.status_code == 200, res.text
        assert handler_spy == []
        errors = _error_records(caplog)
        assert len(errors) == 1
        assert "not_a_real_job" in errors[0].getMessage()

    def test_invalid_base64_data_acks_200_without_calling_handler_and_logs_error(
        self, client, fake_db, handler_spy, caplog
    ):
        with caplog.at_level(logging.ERROR, logger=WORKERS_SERVICES_LOGGER):
            res = client.post(
                PUBSUB_JOB_URL,
                json=_envelope(
                    data="!!!not-valid-base64!!!", message_id="msg-bad-base64"
                ),
            )

        assert res.status_code == 200, res.text
        assert handler_spy == []
        errors = _error_records(caplog)
        assert len(errors) == 1
        assert "msg-bad-base64" in errors[0].getMessage()

    def test_invalid_json_data_acks_200_without_calling_handler_and_logs_error(
        self, client, fake_db, handler_spy, caplog
    ):
        bad_json = base64.b64encode(b"{not valid json").decode("utf-8")
        with caplog.at_level(logging.ERROR, logger=WORKERS_SERVICES_LOGGER):
            res = client.post(
                PUBSUB_JOB_URL,
                json=_envelope(data=bad_json, message_id="msg-bad-json"),
            )

        assert res.status_code == 200, res.text
        assert handler_spy == []
        errors = _error_records(caplog)
        assert len(errors) == 1
        assert "msg-bad-json" in errors[0].getMessage()

    def test_decoded_json_not_an_object_acks_200_without_calling_handler_and_logs_error(
        self, client, fake_db, handler_spy, caplog
    ):
        data = _b64([1, 2, 3])
        with caplog.at_level(logging.ERROR, logger=WORKERS_SERVICES_LOGGER):
            res = client.post(
                PUBSUB_JOB_URL,
                json=_envelope(data=data, message_id="msg-non-object"),
            )

        assert res.status_code == 200, res.text
        assert handler_spy == []
        errors = _error_records(caplog)
        assert len(errors) == 1
        assert "msg-non-object" in errors[0].getMessage()

    def test_missing_data_field_acks_200_without_calling_handler_and_logs_error(
        self, client, fake_db, handler_spy, caplog
    ):
        with caplog.at_level(logging.ERROR, logger=WORKERS_SERVICES_LOGGER):
            res = client.post(
                PUBSUB_JOB_URL,
                json=_envelope(omit_data=True, message_id="msg-missing-data"),
            )

        assert res.status_code == 200, res.text
        assert handler_spy == []
        errors = _error_records(caplog)
        assert len(errors) == 1
        assert "msg-missing-data" in errors[0].getMessage()

    def test_missing_job_type_in_decoded_payload_acks_200_without_calling_handler_and_logs_error(
        self, client, fake_db, handler_spy, caplog
    ):
        data = _b64({"job_id": "job-y", "namespace_id": NS, "payload": {}})
        with caplog.at_level(logging.ERROR, logger=WORKERS_SERVICES_LOGGER):
            res = client.post(PUBSUB_JOB_URL, json=_envelope(data=data))

        assert res.status_code == 200, res.text
        assert handler_spy == []
        errors = _error_records(caplog)
        assert len(errors) == 1
        # job_id is known even though job_type isn't -> the contract requires
        # it to be surfaced in the log.
        assert "job-y" in errors[0].getMessage()

    def test_missing_message_field_acks_200_never_422_and_logs_error(
        self, client, fake_db, handler_spy, caplog
    ):
        with caplog.at_level(logging.ERROR, logger=WORKERS_SERVICES_LOGGER):
            res = client.post(
                PUBSUB_JOB_URL,
                json=_envelope(
                    omit_message=True,
                    subscription="projects/p/subscriptions/missing-message",
                ),
            )

        assert res.status_code == 200, res.text
        assert handler_spy == []
        errors = _error_records(caplog)
        assert len(errors) == 1
        assert "missing-message" in errors[0].getMessage()


# --------------------------------------------------------------------------- #
# 11: no application-level auth (infra OIDC only, like /cloud_job)
# --------------------------------------------------------------------------- #


class TestPubSubJobAuth:
    """/pubsub_job is reached only through the Pub/Sub push subscription,
    authenticated at the infra layer (OIDC) — never by our bearer scheme."""

    def test_no_bearer_token_required(self, client, fake_db, handler_spy):
        data = _b64(
            {"job_id": "job-no-auth", "job_type": KNOWN_JOB_TYPE, "namespace_id": NS}
        )
        res = client.post(PUBSUB_JOB_URL, json=_envelope(data=data))

        assert res.status_code == 200, res.text
        assert len(handler_spy) == 1


# --------------------------------------------------------------------------- #
# 12: non-regression — /cloud_job keeps accepting only the flat Cloud Tasks
# body and rejects the push envelope. Written fresh here; test_down_time.py
# is not touched.
# --------------------------------------------------------------------------- #


class TestCloudJobNonRegression:
    """POST /cloud_job — unaffected by the new /pubsub_job route: still
    Cloud Tasks-only, flat body."""

    def test_cloud_job_still_accepts_flat_cloud_tasks_body(
        self, client, fake_db, handler_spy
    ):
        res = client.post(
            CLOUD_JOB_URL,
            json={
                "job_id": "job-flat",
                "job_type": KNOWN_JOB_TYPE,
                "namespace_id": NS,
                "payload": {"foo": "bar"},
            },
        )

        assert res.status_code == 200, res.text
        assert len(handler_spy) == 1
        assert handler_spy[0]["job_id"] == "job-flat"

    def test_cloud_job_rejects_pubsub_push_envelope_returns_422(self, client, fake_db):
        data = _b64(
            {"job_id": "job-envelope", "job_type": KNOWN_JOB_TYPE, "namespace_id": NS}
        )
        res = client.post(CLOUD_JOB_URL, json=_envelope(data=data))

        assert res.status_code == 422, res.text
