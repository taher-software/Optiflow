---
name: test
description: Use this skill when the Test Agent writes API tests, async handler tests, or integration tests. Provides test framework conventions, fixture patterns, mocking strategies for Pub/Sub and external services, file locations, and naming rules.
---

# Test Skill — Testing Conventions

This skill is consumed exclusively by the Test Agent.
It defines WHERE tests live, HOW they are structured, and the
PROJECT-SPECIFIC conventions for fixtures and mocks.

---

## Test Framework

```
{TO_FILL: e.g., pytest + pytest-django}
```

### Required dev dependencies
```
{TO_FILL: e.g.,
 pytest
 pytest-django
 pytest-mock
 factory-boy
 freezegun
}
```

---

## Test File Locations

| Test type           | Location                              |
|---------------------|---------------------------------------|
| API tests           | `{TO_FILL: e.g., tests/api/}`         |
| Async handler tests | `{TO_FILL: e.g., tests/async_jobs/}`  |
| Integration tests   | `{TO_FILL: e.g., tests/integration/}` |
| Fixtures            | `{TO_FILL: e.g., tests/factories/}`   |
| Test utilities      | `{TO_FILL: e.g., tests/utils/}`       |

**Customize the locations above for this project before first use.**

---

## File Naming

```
Test file:     test_{module_under_test}.py
Test class:    Test{ClassUnderTest}
Test function: test_{behavior_being_verified}
```

Examples:
```
tests/api/test_refunds.py
  class TestCreateRefund:
    def test_admin_can_create_refund(self): ...
    def test_unauthenticated_returns_401(self): ...
    def test_non_admin_returns_403(self): ...
```

---

## Test Scenario Coverage

### For an API endpoint

Required scenarios per endpoint:

```
Happy path
[ ] test_{action}_success

Authentication
[ ] test_unauthenticated_returns_401

Authorization
[ ] test_{forbidden_role}_returns_403

Validation
[ ] test_invalid_{field}_returns_400 (per field with validation)
[ ] test_missing_required_field_returns_400

Resource lookup
[ ] test_{resource}_not_found_returns_404 (if path contains an ID)

Business rules
[ ] test_{rule}_returns_{code} (per rule in upstream contract)

Pagination (if list endpoint)
[ ] test_pagination_default
[ ] test_pagination_custom_page_size

Filters (if applicable)
[ ] test_filter_by_{field}
```

### For an async handler

Required scenarios per handler:

```
Happy path
[ ] test_handler_success

Idempotence
[ ] test_handler_idempotent_on_already_processed

Retry behavior
[ ] test_retryable_failure_triggers_retry
[ ] test_non_retryable_failure_does_not_retry

Edge cases
[ ] test_handler_with_missing_target_resource
[ ] test_handler_with_malformed_payload
```

### For an integration test

```
End-to-end happy path
[ ] test_full_flow_{feature}_success

Failure propagation
[ ] test_{upstream_failure}_propagates_correctly
```

---

## Fixtures (factory-boy convention)

### One factory per model

```python
# tests/factories/refund.py
import factory
from factory.django import DjangoModelFactory
from decimal import Decimal

from refunds.models import Refund
from tests.factories.payment import PaymentFactory


class RefundFactory(DjangoModelFactory):
    class Meta:
        model = Refund

    payment = factory.SubFactory(PaymentFactory)
    amount = Decimal("50.00")
    reason = factory.Faker("sentence", nb_words=6)
    status = "pending"
```

### Rules
- One factory per model
- `SubFactory` for FKs (no hardcoded related IDs)
- `Faker` for fields where real-looking data helps (reason, names)
- Sensible defaults (test will pass without overriding)
- Override only what the test specifically cares about

### Usage in tests

```python
def test_admin_can_list_refunds(admin_client):
    RefundFactory.create_batch(3)
    response = admin_client.get("/api/v1/refunds/")
    assert response.status_code == 200
    assert len(response.json()["results"]) == 3
```

---

## Mocking Conventions

### Pub/Sub publish

When testing an endpoint that publishes a job, the publish call
must be mocked (no real Pub/Sub interaction in tests).

```python
def test_create_refund_publishes_notify_job(admin_client, mocker):
    mock_publish = mocker.patch("path.to.publish_function")

    payment = PaymentFactory()
    response = admin_client.post("/api/v1/refunds/", {
        "payment_id": payment.id,
        "amount": "50.00",
        "reason": "test",
    }, format="json")

    assert response.status_code == 201
    mock_publish.assert_called_once_with(
        job_type="REFUND_NOTIFY",
        payload={"refund_id": response.json()["id"]},
    )
```

### External services

```python
def test_handler_calls_email_service(mocker):
    mock_send = mocker.patch("path.to.email_send")
    refund = RefundFactory()

    handle_refund_notify({"refund_id": refund.id})

    mock_send.assert_called_once()
```

### Time

Use `freezegun` for time-sensitive assertions:

```python
from freezegun import freeze_time

@freeze_time("2024-01-15 10:00:00")
def test_refund_created_at_is_now():
    refund = RefundFactory()
    assert refund.created_at.isoformat() == "2024-01-15T10:00:00+00:00"
```

---

## Test Client Fixtures

Conventional fixtures the test suite provides:

```
client          → unauthenticated DRF APIClient
admin_client    → APIClient authenticated as an admin user
user_client     → APIClient authenticated as a regular user
```

Authentication setup happens in fixtures, not inside tests.

Customize the actual fixture definitions in your project's
`conftest.py` per project conventions.

---

## Async Handler Testing

### Direct handler invocation

For unit-level async tests, call the handler function directly
with a payload — do not go through Pub/Sub.

```python
def test_handler_marks_refund_notified():
    refund = RefundFactory(status="pending")

    handle_refund_notify({"refund_id": refund.id})

    refund.refresh_from_db()
    assert refund.notified_at is not None


def test_handler_is_idempotent():
    refund = RefundFactory(
        status="pending",
        notified_at="2024-01-01T00:00:00Z",
    )
    original_notified_at = refund.notified_at

    handle_refund_notify({"refund_id": refund.id})

    refund.refresh_from_db()
    assert refund.notified_at == original_notified_at
```

### Integration via worker router

For integration tests that go through the full dispatch path,
post to the worker endpoint with the job payload:

```python
def test_worker_route_dispatches_to_handler(client):
    refund = RefundFactory()

    response = client.post("/", {
        "job_type": "REFUND_NOTIFY",
        "payload": {"refund_id": refund.id},
    }, format="json")

    assert response.status_code == 200
```

---

## Test Independence Rules

```
[ ] No order dependencies — tests can run in any order
[ ] No shared mutable state between tests
[ ] No database state leak (use transactions / rollback per test)
[ ] No external service calls (always mocked)
[ ] No time of day dependency (mock if needed)
[ ] No filesystem dependency unless using tmp_path
[ ] No network calls (always mocked)
```

---

## Assertions Style

### Good
```python
assert response.status_code == 201
assert response.json()["amount"] == "50.00"
assert Refund.objects.filter(payment_id=payment.id).exists()
mock_publish.assert_called_once_with(
    job_type="REFUND_NOTIFY",
    payload={"refund_id": ANY},
)
```

### Avoid
```python
# Too vague
assert response.status_code != 500

# Implementation-coupled
assert mock_publish.call_args[0][1]["foo"]["bar"]["baz"] == "x"

# Test does too much
def test_everything():
    # creates, lists, retrieves, updates, deletes — all in one test
```

One test = one behavior.

---

## When Tests Reveal Upstream Bugs

```
1. Write the test correctly, asserting the expected behavior.
2. Mark it as expected_failure or skip with a clear reason.
3. Report an anomaly with severity warning:
   "Test X reveals incorrect behavior in {upstream_unit}:
    expected Y, got Z."
4. Do NOT modify upstream code.
```

Pytest example:

```python
import pytest

@pytest.mark.xfail(reason="Upstream bug: handler does not check status")
def test_handler_skips_already_notified_refund():
    ...
```

---

## Coverage Targets

```
API endpoints       → 100% of documented scenarios
Async handlers      → 100% of documented behaviors
                      (success, idempotence, retry, failure)
Integration tests   → Critical paths only (not every combination)

Coverage % is not the metric — scenario coverage is.
A 95% line coverage with no 401/403/404 tests is a failure.
A 70% line coverage with full scenario coverage may be fine.
```

---

## Quality Bar

Before signaling a Test Work Unit as done:

```
[ ] All scenarios from the upstream contract are covered
[ ] All tests pass locally
[ ] No flaky tests (run the suite twice to confirm)
[ ] No commented-out tests
[ ] No skip markers without justification
[ ] Fixtures use factories (no hardcoded values)
[ ] External services and time are mocked
[ ] Each test name describes the behavior it verifies
```

---

## Anti-Patterns to Avoid

- Tests that pass even when the production code is broken
- Tests coupled to implementation details (private methods, exact SQL)
- Tests that depend on the order of other tests
- Tests that hit real external services
- Tests with no assertions (only side-effect-free function calls)
- Tests with vague names like `test_works`, `test_case_1`
- One giant test that covers many behaviors
- Hardcoded IDs / dates / timestamps without freeze
- Assertions on the count of mock calls when the order matters
  (use `assert_has_calls` with explicit order instead)

---

## Calibration

A pipeline run is healthy when:

```
- Every documented scenario has a test
- All tests pass on first try
- Flakiness is zero
- New tests don't slow the suite materially
```

If tests are routinely added after the fact ("we'll write them later"),
the Test Agent is being skipped or the Planner is missing test units.