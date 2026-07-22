"""API tests for `POST /down-times` (report a downtime) and `POST /cloud_job`
(the async worker entrypoint).

`POST /down-times` only PUBLISHES the `add_down_time` job — it does not run it —
so its tests assert the published message (via the `publish_spy`). The handler's
effects (issue document + push notification) are exercised through the worker
route `POST /cloud_job`, which looks the handler up in the registry and runs it.
"""

import importlib

import pytest

from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeType, JobType, ProductionScope, Role

# The handler submodule (not the package re-export) is where `add_down_time`
# resolves `send_push_notifications`, so that's where the spy must land.
add_down_time_module = importlib.import_module("src.app.async_jobs.add_down_time")

NS = "ns-downtime"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    """The add_down_time handler now requires the namespace to exist."""
    seed_namespace(id=NS)


@pytest.fixture(autouse=True)
def _auto_publish(publish_spy):
    """Activate the Pub/Sub publisher spy for every test: `POST /down-times`
    publishes rather than running the handler, so real Pub/Sub is never hit."""
    return publish_spy


@pytest.fixture
def push_spy(monkeypatch):
    """Spy on the Expo push send, recording each call's tokens/title/body."""
    calls: list[dict] = []

    def _spy(tokens, title, body, data=None):
        calls.append(
            {"tokens": list(tokens), "title": title, "body": body, "data": data}
        )

    monkeypatch.setattr(add_down_time_module, "send_push_notifications", _spy)
    return calls


def _issue(fake_db, namespace_id, job_id):
    """Read back an issue document written by the in-process handler."""
    return FirestoreClient(client=fake_db).get_subdocument(
        "down_time", namespace_id, "issues", job_id
    )


def _agent(seed_user, **overrides):
    overrides.setdefault("namespace_id", NS)
    overrides.setdefault("role", Role.PRODUCTION_AGENT.value)
    return seed_user(**overrides)


# --------------------------------------------------------------------------- #
# Happy paths — the endpoint PUBLISHES the job (it does not run it in-process),
# so we assert the published message, not a synchronous write.
# --------------------------------------------------------------------------- #


class TestCreateDownTime:
    def test_plant_breakdown_returns_202_and_publishes(
        self, client, seed_user, auth_headers, publish_spy
    ):
        agent = _agent(seed_user)
        res = client.post(
            "/down-times",
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PLANT.value,
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 202, res.text
        job_id = res.json()["data"]["job_id"]
        assert job_id

        assert len(publish_spy) == 1
        call = publish_spy[0]
        assert call["job_type"] == JobType.ADD_DOWN_TIME
        assert call["namespace_id"] == NS
        assert call["job_id"] == job_id
        assert call["payload"]["created_by"] == agent["id"]
        assert call["payload"]["production_scope"] == "plant"
        assert call["payload"]["down_time_type"] == "break down"
        assert call["payload"]["uap_id"] is None

    def test_uap_scope_publishes_uap_id(
        self, client, seed_user, seed_uap, auth_headers, publish_spy
    ):
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        res = client.post(
            "/down-times",
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.UAP.value,
                "uap_id": uap["id"],
                "down_time_type": DownTimeType.QUALITY_ISSUE.value,
            },
        )
        assert res.status_code == 202, res.text
        assert publish_spy[0]["payload"]["production_scope"] == "uap"
        assert publish_spy[0]["payload"]["uap_id"] == uap["id"]

    def test_workstation_scope_publishes_full_chain(
        self,
        client,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
        publish_spy,
    ):
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        res = client.post(
            "/down-times",
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.WORK_STATION.value,
                "uap_id": uap["id"],
                "production_line_id": line["id"],
                "workstation_id": station["id"],
                "down_time_type": DownTimeType.MATERIAL_SHORTAGE.value,
            },
        )
        assert res.status_code == 202, res.text
        payload = publish_spy[0]["payload"]
        assert payload["workstation_id"] == station["id"]
        assert payload["production_line_id"] == line["id"]

    def test_setup_changeover_publishes_department(
        self, client, seed_user, auth_headers, publish_spy
    ):
        agent = _agent(seed_user)
        res = client.post(
            "/down-times",
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PLANT.value,
                "down_time_type": DownTimeType.SETUP_CHANGEOVER.value,
                "department": "maintenance",
            },
        )
        assert res.status_code == 202, res.text
        assert publish_spy[0]["payload"]["department"] == "maintenance"


# --------------------------------------------------------------------------- #
# Validation (422)
# --------------------------------------------------------------------------- #


class TestCreateDownTimeValidation:
    def _post(self, client, auth_headers, agent, **body):
        return client.post("/down-times", headers=auth_headers(agent), json=body)

    def test_setup_changeover_without_department_422(
        self, client, seed_user, auth_headers
    ):
        agent = _agent(seed_user)
        res = self._post(
            client,
            auth_headers,
            agent,
            production_scope="plant",
            down_time_type=DownTimeType.SETUP_CHANGEOVER.value,
        )
        assert res.status_code == 422

    def test_setup_changeover_wrong_department_422(
        self, client, seed_user, auth_headers
    ):
        agent = _agent(seed_user)
        res = self._post(
            client,
            auth_headers,
            agent,
            production_scope="plant",
            down_time_type=DownTimeType.SETUP_CHANGEOVER.value,
            department="quality",
        )
        assert res.status_code == 422

    def test_department_on_non_setup_type_422(self, client, seed_user, auth_headers):
        agent = _agent(seed_user)
        res = self._post(
            client,
            auth_headers,
            agent,
            production_scope="plant",
            down_time_type=DownTimeType.BREAKDOWN.value,
            department="maintenance",
        )
        assert res.status_code == 422

    def test_uap_scope_without_uap_id_422(self, client, seed_user, auth_headers):
        agent = _agent(seed_user)
        res = self._post(
            client,
            auth_headers,
            agent,
            production_scope="uap",
            down_time_type=DownTimeType.BREAKDOWN.value,
        )
        assert res.status_code == 422

    def test_line_scope_without_line_id_422(self, client, seed_user, auth_headers):
        agent = _agent(seed_user)
        res = self._post(
            client,
            auth_headers,
            agent,
            production_scope="production line",
            down_time_type=DownTimeType.BREAKDOWN.value,
        )
        assert res.status_code == 422

    def test_station_scope_without_station_id_422(
        self, client, seed_user, auth_headers
    ):
        agent = _agent(seed_user)
        res = self._post(
            client,
            auth_headers,
            agent,
            production_scope="work station",
            down_time_type=DownTimeType.BREAKDOWN.value,
        )
        assert res.status_code == 422

    def test_nonexistent_uap_id_422(self, client, seed_user, auth_headers):
        agent = _agent(seed_user)
        res = self._post(
            client,
            auth_headers,
            agent,
            production_scope="uap",
            uap_id="does-not-exist",
            down_time_type=DownTimeType.BREAKDOWN.value,
        )
        assert res.status_code == 422

    def test_cross_namespace_uap_id_422(
        self, client, seed_user, seed_uap, auth_headers
    ):
        agent = _agent(seed_user)
        other_uap = seed_uap(namespace_id="other-ns")
        res = self._post(
            client,
            auth_headers,
            agent,
            production_scope="uap",
            uap_id=other_uap["id"],
            down_time_type=DownTimeType.BREAKDOWN.value,
        )
        assert res.status_code == 422

    def test_line_belonging_to_other_uap_422(
        self, client, seed_user, seed_uap, seed_production_line, auth_headers
    ):
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        other_uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=other_uap["id"])
        res = self._post(
            client,
            auth_headers,
            agent,
            production_scope="production line",
            uap_id=uap["id"],
            production_line_id=line["id"],
            down_time_type=DownTimeType.BREAKDOWN.value,
        )
        assert res.status_code == 422

    def test_station_belonging_to_other_line_422(
        self,
        client,
        seed_user,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        agent = _agent(seed_user)
        line = seed_production_line(namespace_id=NS, uap_id=None)
        other_line = seed_production_line(namespace_id=NS, uap_id=None)
        station = seed_workstation(
            namespace_id=NS, production_line_id=other_line["id"]
        )
        res = self._post(
            client,
            auth_headers,
            agent,
            production_scope="work station",
            production_line_id=line["id"],
            workstation_id=station["id"],
            down_time_type=DownTimeType.BREAKDOWN.value,
        )
        assert res.status_code == 422

    def test_blank_uap_id_422(self, client, seed_user, auth_headers):
        agent = _agent(seed_user)
        res = self._post(
            client,
            auth_headers,
            agent,
            production_scope="plant",
            uap_id="   ",
            down_time_type=DownTimeType.BREAKDOWN.value,
        )
        assert res.status_code == 422


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #


class TestCreateDownTimeAuthz:
    @pytest.mark.parametrize(
        "role",
        [
            Role.MAINTENANCE_AGENT.value,
            Role.ADMIN.value,
            Role.OWNER.value,
            Role.PRODUCTION_SUPERVISOR.value,
        ],
    )
    def test_non_production_agent_forbidden(
        self, client, seed_user, auth_headers, role
    ):
        user = seed_user(namespace_id=NS, role=role)
        res = client.post(
            "/down-times",
            headers=auth_headers(user),
            json={
                "production_scope": "plant",
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 403

    def test_no_token_401(self, client):
        res = client.post(
            "/down-times",
            json={
                "production_scope": "plant",
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 401


# --------------------------------------------------------------------------- #
# Notification targeting — driven through the worker route (which runs the
# handler), since the create endpoint now only publishes.
# --------------------------------------------------------------------------- #


def _dispatch_breakdown(client, job_id="job-notif"):
    return client.post(
        "/cloud_job",
        json={
            "job_id": job_id,
            "job_type": "add_down_time",
            "namespace_id": NS,
            "payload": {
                "created_by": "opener",
                "production_scope": "plant",
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        },
    )


class TestDownTimeNotifications:
    def test_notifies_only_online_process_agents_with_tokens(
        self, client, seed_user, push_spy
    ):
        # Target process for a break down is "maintenance".
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True, push_token="tok-online",
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            push_token="tok-default",  # no `online` field -> online by default
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=False, push_token="tok-offline",
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=True,  # no push_token -> excluded
        )
        seed_user(
            namespace_id=NS, role=Role.QUALITY_AGENT.value,
            online=True, push_token="tok-quality",  # wrong process -> excluded
        )
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_SUPERVISOR.value,
            online=True, push_token="tok-supervisor",  # not an agent -> excluded
        )

        res = _dispatch_breakdown(client)
        assert res.status_code == 200
        assert len(push_spy) == 1
        assert set(push_spy[0]["tokens"]) == {"tok-online", "tok-default"}
        assert push_spy[0]["data"]["process"] == "maintenance"

    def test_no_online_agents_still_succeeds(self, client, seed_user, push_spy):
        seed_user(
            namespace_id=NS, role=Role.MAINTENANCE_AGENT.value,
            online=False, push_token="tok",
        )
        res = _dispatch_breakdown(client)
        assert res.status_code == 200
        # No online maintenance agent -> push not sent, job still acked.
        assert push_spy == []


# --------------------------------------------------------------------------- #
# Worker route
# --------------------------------------------------------------------------- #


class TestCloudJobWorker:
    def test_cloud_job_unauthenticated_dispatches_and_acks(
        self, client, fake_db, seed_user, push_spy
    ):
        agent = _agent(seed_user)
        job_id = "job-worker-1"
        res = client.post(
            "/cloud_job",
            json={
                "job_id": job_id,
                "job_type": "add_down_time",
                "namespace_id": NS,
                "payload": {
                    "created_by": agent["id"],
                    "production_scope": "plant",
                    "down_time_type": DownTimeType.BREAKDOWN.value,
                },
            },
        )
        assert res.status_code == 200, res.text
        assert _issue(fake_db, NS, job_id) is not None
        # The worker route surfaces the handler's own response.
        assert res.json()["data"]["result"]["status"] == "created"

    def test_cloud_job_unknown_job_type_still_acks_200(self, client):
        res = client.post(
            "/cloud_job",
            json={
                "job_type": "not_a_real_job",
                "namespace_id": NS,
                "payload": {},
            },
        )
        assert res.status_code == 200
