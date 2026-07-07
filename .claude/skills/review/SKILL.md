---
name: review
description: Use this skill when the Review Agent performs per-component or cross-cutting code review. Provides the severity rubric, checklists per layer (DB, API, Async), security focus areas, performance heuristics, and project-specific anti-patterns to catch.
---

# Review Skill — Code Review Rubric

This skill is consumed exclusively by the Review Agent.
It defines the categories to check, the severity rubric, the
project-specific anti-patterns, and the scoring formula.

---

## Severity Rubric

```
blocking
- Security vulnerability (auth bypass, injection, data leak)
- Data integrity risk (corruption, loss, inconsistency)
- Breaks the upstream documented contract
- Crashes / unhandled exceptions on common paths
- Migration that destroys data without rollback path
- Sensitive data in logs

warning
- Performance issue likely under load (N+1, missing index)
- Missing edge case handling
- Convention drift that hurts maintainability
- Documentation contradicts code
- Idempotence weakness in async handler
- Race condition in non-critical path

info
- Style improvements
- Optional refactoring opportunities
- Learning suggestions
- Naming nits
```

---

## Scoring Formula

```
Start at 100.
Subtract per finding:
  blocking → -15
  warning  →  -3
  info     →  -1

Floor at 0.

Score is informational. Severity counts are what the
developer reads first.
```

---

## Per-Component Review Checklists

### DB Layer (review.X_db)

**Models**
- [ ] Every model has `__str__`, `Meta`, `verbose_name`
- [ ] `created_at` / `updated_at` present where applicable
- [ ] All FKs have explicit `on_delete` behavior
- [ ] No business logic in model methods (only data operations)
- [ ] No print/debug statements

**Indexes**
- [ ] Every field used in `filter()`, `order_by()`, `unique=True` has an index
- [ ] Composite indexes for queries that filter on multiple fields
- [ ] No redundant indexes (single-field index when composite already covers it)

**Migrations**
- [ ] One migration per logical change
- [ ] Reversible (or documented reason if not)
- [ ] No data migration mixed with schema migration in the same file
- [ ] No destructive operations (DROP, TRUNCATE) without explicit approval
- [ ] Tested forward + reverse locally

**Naming**
- [ ] `snake_case` for tables and fields
- [ ] FK fields named `{model}_id`
- [ ] No abbreviations (`amt`, `cnt`, `desc`)

**Security**
- [ ] No hardcoded secrets in defaults / fixtures
- [ ] Sensitive fields marked `write_only` in serializer context
- [ ] PII fields documented as such

---

### API Layer (review.X_api)

**REST conventions**
- [ ] HTTP methods used correctly (GET / POST / PUT / PATCH / DELETE)
- [ ] Versioning present (`/api/v1/...`)
- [ ] Status codes appropriate (200/201/204/400/401/403/404/409/422)

**Serializers**
- [ ] Validation in `validate_{field}` and `validate()`
- [ ] `read_only_fields` explicit
- [ ] No business logic inside serializers
- [ ] Nested serializers documented

**Views / ViewSets**
- [ ] Explicit permission classes (never relies on defaults silently)
- [ ] Authentication required by default (opt-out documented)
- [ ] No N+1: uses `select_related` / `prefetch_related`
- [ ] Pagination on list endpoints
- [ ] Filters use a documented mechanism (django-filter or explicit query params)

**URLs**
- [ ] Routes registered in `urls.py` or via router
- [ ] URL patterns follow resource conventions

**Security**
- [ ] Rate limiting on public endpoints
- [ ] Sensitive fields `write_only` or excluded from output
- [ ] Error messages do not leak internal state
- [ ] CSRF / CORS configured (or documented as N/A)

---

### Async Layer (review.X_async)

**Job type & registration**
- [ ] Job type added in the documented enum location
- [ ] Handler registered in the documented dispatch table
- [ ] Handler signature matches the dispatcher contract

**Idempotence**
- [ ] Handler can be safely re-invoked on retry
- [ ] Side effects (emails, payments, external calls) protected by
      deduplication key or state check
- [ ] State transitions are conditional (no blind writes)

**Retry & failure handling**
- [ ] Retryable vs non-retryable failures distinguished
- [ ] Logging at start and end of handler with key parameters
- [ ] Non-retryable failures fail fast without retry exhaustion
- [ ] Dead letter handling per project conventions

**Publish call**
- [ ] Publish placed at the correct trigger point
- [ ] Payload follows the documented schema
- [ ] No sensitive data in the payload
- [ ] No DB writes blocking the publish path beyond what's documented

**Naming**
- [ ] Job type names follow project conventions
- [ ] Handler function names follow project conventions

---

## Cross-Cutting Review Checklist (review.X_crosscut)

Focus on consistency that only surfaces at the seams:

**Consistency**
- [ ] Field names match across DB, API, Async (same entity = same names)
- [ ] Types match across layers (DecimalField → Decimal in serializer → Decimal in payload)
- [ ] Status values match across model choices, serializer validation, async events

**Acceptance criteria alignment**
- [ ] Every acceptance criterion in `feature.md` is observably achieved
- [ ] No criterion silently dropped or reinterpreted

**Repeated logic**
- [ ] No duplicated validation logic across serializer and async handler
- [ ] No duplicated permission logic across views

**Seam security**
- [ ] An endpoint that triggers a task does not let the task bypass
      endpoint-level permissions
- [ ] A PubSub event payload does not expose data the endpoint hides
- [ ] Webhook handlers validate signatures

**Seam performance**
- [ ] No N+1 caused by serializers triggering tasks
- [ ] No accidental synchronous chain (endpoint → task → task → ...)

**Documentation alignment**
- [ ] User docs reflect actual behavior
- [ ] Error codes documented in API docs match error codes raised

---

## Project-Specific Anti-Patterns

```
{TO_FILL: list project-specific anti-patterns to flag, e.g.:}

- Bypassing the service layer by calling ORM directly from views
- Direct PubSub publish inside a transaction (publish before commit)
- Using `select_related` without specifying fields
- Catching Exception broadly without re-raise
- ...
```

**Customize this list with your team's recurring issues.**

---

## Security Focus Areas

**Always check**
- Authentication present and correct on every endpoint
- Authorization (permissions) explicit on every endpoint
- Input validation on every user-controlled field
- Output sanitization for any field that may contain user input
  rendered elsewhere
- Secrets not in code, not in logs, not in payloads
- SQL injection impossible (ORM used correctly, no raw SQL with
  user input)

**Often missed**
- IDOR (insecure direct object reference) on `/resource/{id}/`
- Mass assignment via permissive serializer fields
- Sensitive data leak through error messages
- Sensitive data leak through PubSub payloads to subscribers
  that should not see it
- Timing attacks on auth endpoints

---

## Performance Heuristics

```
- For every queryset that produces N rows, count the queries:
  if it's N+1, flag it as warning
- For every list endpoint, verify pagination is applied
- For every async handler, verify it doesn't hold DB connections
  longer than necessary
- For every cross-service call, verify timeout is set
- For every retry, verify the backoff strategy
```

---

## Output Quality Rules

When writing findings:

```
Good finding:
  Location: src/refunds/views.py:42
  Severity: warning
  Description: N+1 query — RefundViewSet.list() accesses
    refund.payment in the serializer, triggering one query
    per refund.
  Suggestion: Add prefetch_related("payment") to the queryset
    in RefundViewSet.get_queryset().

Bad finding:
  Severity: warning
  Description: This is slow.
  Suggestion: Make it faster.
```

Every finding must have:
- **Location** (file + line when applicable)
- **Severity** (per rubric)
- **Description** (what is wrong, concretely)
- **Suggestion** (a fix, not a wish)

---

## What Review Agent Should NOT Flag

- Personal style preferences not in the rubric
- Existing code outside the unit's scope
- Patterns the codebase already uses elsewhere (unless they are
  themselves wrong)
- Speculative future problems ("might be an issue if...")

---

## Calibration

A pipeline run is healthy when:

```
- Most units score 85+
- Blocking findings are rare (< 1 per 3 units on average)
- Warnings are mostly real issues, not noise
```

If most findings are info-level, the rubric is too soft.
If most units score < 70, either the rubric is too harsh or
the upstream agents need attention.

Adjust the rubric over time based on what produces real
improvements in merged code.