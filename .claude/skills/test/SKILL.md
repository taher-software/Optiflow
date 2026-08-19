---
name: test
description: Use this skill when the Test Agent writes API tests, async handler tests, or integration tests. Provides test framework conventions, fixture patterns, mocking strategies for Pub/Sub and external services, file locations, and naming rules.
---

# Test Skill — Testing Conventions

Consumed by the **Test Agent**. Defines WHERE tests live, HOW they are structured, and the
project-specific conventions for fixtures and mocks.

**Stack: FastAPI · Firestore · Pydantic · Pub/Sub · Cloud Tasks. There is no ORM, no
database, no migrations.** Every convention below is written for that stack — do not
import Django/DRF idioms (`DjangoModelFactory`, `pytest-django`, `APIClient`,
`.objects.filter`, `refresh_from_db`, `format="json"`). They do not exist here.

---

## Framework & how to run

```
pytest 9 · pytest-mock · factory-boy · Faker · httpx (via fastapi.testclient.TestClient)
```

Run from `backend/`:

```bash
./.venv/bin/python -m pytest -q                     # whole suite (~12s, 572 tests)
./.venv/bin/python -m pytest tests/api/test_x.py -q # one module
./.venv/bin/python -m pytest -q -p no:randomly      # (if ordering is ever added)
```

**Not installed, do not import:** `freezegun`, `pytest-django`, `pytest-asyncio`,
`pytest-cov`. Time is controlled by monkeypatching (see *Controlling time*). If a Work
Unit genuinely needs a new dev dependency, raise an anomaly — do not add it silently.

There is no `requirements-dev.txt` and no `pytest.ini`. Test deps live in the `.venv`;
`tests/conftest.py` puts `backend/` on `sys.path`, so imports are always absolute from the
repo root (`src.app...`, `tests...`).

---

## Test file locations

| Test type | Location |
|---|---|
| API tests | `tests/api/` |
| Async handler tests | `tests/async_jobs/` |
| Integration tests | `tests/integration/` |
| Factories | `tests/factories/` |
| Core/helper unit tests | `tests/core/`, `tests/globals/` |
| Firestore double | `tests/fake_firestore.py` |
| Shared fixtures | `tests/conftest.py` (+ local `conftest.py` per directory) |

`tests/core/` and `tests/globals/` cover pure helpers (escalation scheduling, notification
copy, timezone resolution, push payloads). **The Test Agent owns `api/`, `async_jobs/`,
and `integration/`.** Touch `core/`/`globals/` only when a Work Unit explicitly says so.

---

## Naming

```
File:      test_{module_under_test}.py
Class:     class Test{ThingUnderTest}:      + one-line docstring naming the route/handler
Function:  def test_{behavior}_{expected_outcome}(...)
```

Real examples from this suite:

```python
class TestCreateWorkstation:
    """POST /workstations"""

    def test_create_workstation_independent_returns_201(...)
    def test_create_workstation_cross_namespace_line_id_returns_422(...)
    def test_create_workstation_unauthenticated_returns_401(...)
```

Names end in the observable outcome (`_returns_201`, `_is_idempotent`,
`_does_not_retry`). Never `test_works`, `test_case_1`.

Every test module opens with a docstring stating **which source files it covers**, which
behaviors, and any notable exclusion ("no timestamps in this contract, so time is not
frozen here").

Module-level constants for URLs and roles, right after the imports:

```python
WORKSTATIONS_URL = "/workstations"
FORBIDDEN_ROLE = Role.MAINTENANCE_AGENT.value   # a role NOT permitted here, for 403 tests
```

---

## The fixtures (from `tests/conftest.py`)

| Fixture | What it gives you |
|---|---|
| `client` | `TestClient(app)`, unauthenticated |
| `fake_db` | fresh in-memory `FakeFirestore` per test, wired into every service module |
| `auth_headers` | `auth_headers(user) -> {"Authorization": "Bearer ..."}` |
| `seed_user` | `seed_user(role=..., namespace_id=...) -> user dict` |
| `seed_namespace` / `seed_uap` / `seed_production_line` / `seed_workstation` | seed a doc straight into `fake_db` |
| `publish_spy` | records Pub/Sub `publish_job` calls instead of publishing |
| `_no_real_network` | **autouse** guard: any real Resend/Expo egress fails the test |

Rules:

- **Authentication happens in fixtures, never inline in a test.** Build the caller with
  `seed_user(role=...)` and pass `headers=auth_headers(caller)`.
- A test that asserts a `401` still needs `fake_db` in its signature — the fixture is what
  keeps the app off real Firestore even when the request never gets that far.
- Seed *prerequisite* resources through `seed_*` (direct doc write); exercise the
  *resource under test* through its endpoint. A local `_create_x(...)` helper that posts to
  a sibling endpoint is fine when the real cross-resource wiring is what matters.

### The monkeypatch gotcha — read before adding a new patch

Every module does `from ... import get_firestore_client`, which **binds its own name** in
that module's globals. Patching the definition site does nothing to a module that already
imported it. Patch the module whose function body makes the call:

```python
monkeypatch.setattr(down_time_services_module, "get_firestore_client", lambda: client)
```

Same trap for `send_push_notifications`, `_send`, `schedule_escalation`, and for anything
re-exported from a package `__init__.py` — import the **submodule**
(`importlib.import_module("src.app.async_jobs.add_down_time")`), not the package.

**A new service module means a new `monkeypatch.setattr` line in the `fake_db` fixture.**
Forgetting it makes the service hit real Firestore.

### The network guard

`_no_real_network` is autouse and patches the two true egress points
(`core.push.requests`, `core.email._send`). It both raises *and* records the attempt,
because production senders swallow exceptions by design — the teardown assertion is what
production code cannot swallow. Never weaken or bypass it; add a `push_spy`/`email_spy`
style monkeypatch on the module under test instead.

---

## Factories (factory-boy, `model = dict`)

Firestore is schemaless, so factories build **plain dicts**, not model instances:

```python
class UserFactory(factory.Factory):
    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    namespace_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    email = factory.Faker("email")
    role = Role.MAINTENANCE_AGENT.value
```

Rules:

- One factory module per resource, in `tests/factories/`.
- **Split payload vs document** when they differ: `WorkstationPayloadFactory` (the JSON
  request body) and `WorkstationDocFactory` (the stored Firestore doc, as the service
  writes it). Docs carry `id` + `namespace_id`; payloads do not.
- **No `SubFactory` for relations** — there are no FKs. Relations are id strings; pass
  them explicitly (`WorkstationDocFactory(production_line_id=line["id"])`) so the test
  states the relationship it depends on.
- `LazyFunction(lambda: str(uuid.uuid4()))` for ids, `Faker` for human-ish fields, enum
  `.value` for enum fields.
- Defaults must make the factory usable with **zero overrides**; a test overrides only
  what it is about.
- Every factory module gets a docstring naming the service function whose written shape it
  mirrors.

---

## Required scenario coverage

Scenario coverage is the metric — **not line percentage**. Full line coverage with no
`401`/`403`/cross-namespace test is a failed Work Unit.

### Per API endpoint

```
Happy path
[ ] test_{action}_returns_{2xx}                     one per meaningful success shape

Authentication
[ ] test_{action}_unauthenticated_returns_401

Authorization
[ ] test_{action}_forbidden_role_returns_403        use the module's FORBIDDEN_ROLE

Tenant isolation  ── MANDATORY, every endpoint that reads or writes a document
[ ] test_{action}_cross_namespace_returns_404       another tenant's doc is invisible
[ ] test_list_{resource}_returns_only_caller_namespace
[ ] test_{action}_cross_namespace_{ref}_id_returns_422   a referenced id from another tenant

Validation                                          FastAPI/Pydantic → 422, never 400
[ ] test_{action}_missing_{required_field}_returns_422
[ ] test_{action}_invalid_{field}_returns_422       per validated field / enum
[ ] test_{action}_blank_{ref}_id_returns_422

Resource lookup
[ ] test_{action}_not_found_returns_404             whenever the path carries an id

Business rules
[ ] test_{rule}_returns_{code}                      one per rule in the contract

Side effects
[ ] test_{action}_publishes_{job_type}              assert on publish_spy
[ ] test_{action}_leaves_doc_unchanged_on_error     any rejected write

Lists
[ ] test_filter_by_{field}                          per supported filter
```

Add pagination scenarios only where the endpoint actually paginates.

### Per async handler

```
[ ] test_handler_success
[ ] test_handler_is_idempotent_on_already_processed
[ ] test_retryable_failure_retries                  assert the call count
[ ] test_non_retryable_failure_does_not_retry
[ ] test_handler_missing_{resource}_...             target document absent
[ ] test_handler_malformed_payload_...
[ ] test_notification_failure_does_not_fail_the_job  where sends are best-effort
```

### Per integration path

```
[ ] test_full_flow_{feature}_success                endpoint → publish → handler → side effect
[ ] test_{upstream_failure}_propagates_correctly
```

---

## Status codes in this codebase

| Situation | Code |
|---|---|
| Created | `201` |
| Read / update / delete | `200` |
| No bearer token, or invalid one | `401` |
| Authenticated but role not permitted | `403` |
| Not found **and** another tenant's document | `404` |
| Pydantic validation, bad enum, unknown/blank/cross-tenant referenced id | `422` |
| Conflicting state transition (business rule) | `409` |
| `/cloud_job` worker route — **always**, success or handler failure | `200` |

Cross-tenant reads are `404`, not `403`: another tenant's document must not be
distinguishable from a nonexistent one.

The worker route never signals failure by status — retry is owned by the handler's
`backoff` decorator, so a non-2xx would make the transport redeliver forever. Assert
handler behavior directly, not the route's status.

---

## Response envelope

Every endpoint returns `ApiResponse`: `{"success", "message", "data"}`. Assert through it:

```python
assert response.status_code == 201
data = response.json()["data"]
assert data["name"] == "Press 1"
assert data["namespace_id"] == owner["namespace_id"]
```

---

## Mocking

### Pub/Sub

Use `publish_spy` and assert on the recorded call — an endpoint **publishes**, it never
runs the handler in-process, and a test must never make it do so:

```python
def test_create_down_time_publishes_add_down_time(client, seed_user, auth_headers, publish_spy):
    ...
    assert len(publish_spy) == 1
    assert publish_spy[0]["job_type"] == JobType.ADD_DOWN_TIME.value
    assert publish_spy[0]["payload"]["workstation_id"] == station["id"]
```

### Cloud Tasks / escalation

`tests/async_jobs/conftest.py` stubs `_common.schedule_escalation` to a fast success by
default (the real one constructs a `CloudTasksClient`). A test that cares about escalation
overrides that stub with its own spy on the same `monkeypatch`.

### Email & push

Monkeypatch the caller-facing helper **on the module under test**
(`add_down_time_module.send_push_notifications`). The autouse network guard sits
underneath as a backstop, not as your mock.

### Firestore

Never mocked with `MagicMock` — use the real `fake_db`. Assert state by **reading the
document back**:

```python
assert fake_db.collection(WORKSTATION_COLLECTION).document(station_id).get().to_dict()["name"] == "Press 2"
```

### Controlling time

`freezegun` is not installed. Freeze time by monkeypatching the `datetime` name in the
module under test:

```python
class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 3, 1, 8, 0, tzinfo=tz or timezone.utc)

monkeypatch.setattr(kpi_services_module, "datetime", _FixedDatetime)
```

Any assertion touching a timestamp, a shift window, an SLA delay, or an escalation deadline
must pin time this way.

---

## Async handler tests

Call the handler **directly** with its payload — never through Pub/Sub:

```python
def test_add_down_time_creates_the_ticket(fake_db, seed_workstation, seed_namespace):
    ...
    add_down_time(namespace_id=ns["id"], payload={...})
    ...assert by reading the document back...
```

Handlers are `backoff`-decorated. `tests/async_jobs/conftest.py` no-ops `time.sleep`, so
retry tests assert **call counts and final outcome**, never elapsed time.

Idempotence tests seed the already-processed state, invoke the handler again, and assert
nothing changed — including that no second notification was sent.

---

## Independence

```
[ ] Any order — no test depends on another having run
[ ] No shared mutable state (fake_db is function-scoped; keep it that way)
[ ] No real network, Firestore, Pub/Sub, Cloud Tasks, Resend, or Expo
[ ] No dependency on wall-clock time or the machine's timezone
[ ] No filesystem writes outside tmp_path
[ ] Deterministic: run twice, same result
```

---

## Assertion style

**Good**

```python
assert response.status_code == 422
assert fake_db.collection(UAP_COLLECTION).document(uap["id"]).get().to_dict() == original
assert publish_spy[0]["job_type"] == JobType.ADD_DOWN_TIME.value
```

**Avoid**

```python
assert response.status_code != 500                 # vague
assert mock.call_args[0][1]["a"]["b"]["c"] == "x"  # implementation-coupled
def test_everything(): ...                          # create+list+update+delete in one test
```

One test = one behavior. Arrange / act / assert, separated by a blank line.

---

## Test-first mode (the human validation gate)

When a Work Unit is dispatched **before** the implementation exists, the deliverable is a
suite that fails for the right reason:

1. Derive scenarios from the contract (`endpoints.md` / `jobs.md`, the BOM entry) —
   **never** from implementation code. If the contract is ambiguous or silent on a
   scenario, raise an anomaly rather than inventing the behavior.
2. Write the full suite, including fixtures and factories, so it is runnable as-is.
3. Run it and capture the output. Every test must fail on **its own assertion or on the
   missing endpoint/handler** — not on a broken fixture, import error, or typo. A fixture
   or factory bug at this stage is a defect in the deliverable.
4. Hand back: the scenario list in plain language, the run output, and one line per test
   naming the reason it currently fails.
5. Once validated by the developer, **the test files are frozen.** No agent — including
   you on a later unit — edits a validated test to make code pass. A validated test that
   turns out to be wrong is an anomaly raised back to the developer.

---

## When tests reveal an upstream bug

1. Write the test asserting the **expected** behavior.
2. Mark it `@pytest.mark.xfail(reason="Upstream bug: ...")` with a concrete reason.
3. Raise an anomaly at `warning` severity: "Test X reveals incorrect behavior in
   {unit}: expected Y, got Z."
4. **Never modify upstream production code.**

---

## Quality bar — before signalling done

```
[ ] Every contract scenario covered, tenant isolation included
[ ] ./.venv/bin/python -m pytest -q is green (or, in test-first mode, red for the right reasons)
[ ] Suite run twice, same result — no flakes
[ ] Any new service module added to the fake_db fixture's patch list
[ ] No commented-out tests, no unexplained skips
[ ] Data comes from factories, not hardcoded literals
[ ] Time, Pub/Sub, Cloud Tasks, email, push all controlled
[ ] Each test name states the behavior and its outcome
[ ] Module docstring names the source files covered
```

---

## Anti-patterns

- Tests that still pass when the production code is broken.
- Asserting `!= 500`, or asserting only the status code on a happy path.
- Patching `get_firestore_client` at its definition site instead of the calling module.
- `MagicMock` in place of `fake_db`.
- Making an endpoint run its async handler in-process instead of asserting the publish.
- Skipping the cross-namespace test because "the query obviously filters by tenant".
- Django/DRF idioms — this project has no ORM.
- One giant test covering create → list → update → delete.
