# BOM — Subscription status on login

Feature branch: `feature/login-subscription-status`.
Status: **VALIDATED** — bucket A ruled on by the developer (2026-09-18).
The developer waived the test-first gate: no new test suite is written up
front; existing tests that assert the login response shape are updated to
match this contract.

Depends on: `.claude/specs/subscription-plans.md` (namespace subscription
fields, `PLAN_COLLECTION`).

## 1. Goal

Every login response tells the client (web + mobile) the state of the
tenant's **base** subscription, so the UI can warn or block.

## 2. Affected endpoints

All three return `LoginOut` via `auth.services._build_login_out`:

- `POST /auth/login` (web)
- `POST /auth/mobile-login` (mobile)
- `POST /auth/check-user-code` (mobile pairing)

## 3. `LoginOut` — four new root-level fields

Added at the **root** of `LoginOut` (next to `access_token`), NOT inside `user`:

| Field | Type | Default |
|---|---|---|
| `warning` | `Optional[bool]` | `None` |
| `blocked` | `Optional[bool]` | `None` |
| `plan_id` | `Optional[str]` | `None` |
| `plan_name` | `Optional[str]` | `None` |

## 4. Computation

Read the user's namespace document (`NAMESPACE_COLLECTION`, id =
`user.namespace_id`). Only the **base** subscription is considered:
`subscription_plan_id`, `subscription_end_date`. Every `extra_*` field and
`oiu_generated` are ignored.

- "today" = current date in the namespace timezone
  (`core.timezone.namespace_timezone`, UTC fallback).
- `end_date` = `subscription_end_date` parsed as ISO `YYYY-MM-DD`. The end
  date itself is still covered.
- `days_expired = (today - end_date).days`

| Situation | `warning` | `blocked` |
|---|---|---|
| No `subscription_end_date` (null / missing key / no namespace doc) | `null` | `null` |
| `days_expired <= 0` (active, incl. the end date itself) | `null` | `null` |
| `1 <= days_expired <= 29` | `true` | `false` |
| `days_expired >= 30` | `false` | `true` |

Example: `end_date = 2026-09-01` → warning from 2026-09-02, blocked from
2026-10-01.

`plan_id` / `plan_name`: when `subscription_plan_id` is set, `plan_id` = that
id and `plan_name` = the `name` of the matching `PLAN_COLLECTION` document —
**returned whether the subscription is active or expired**. No
`subscription_plan_id` → both `null`. Plan document missing → `plan_id` set,
`plan_name` `null`.

`blocked` is **informational only**: login still succeeds (`200` + token). The
backend refuses nothing based on it; web/mobile decide what to show.

## 5. Out of scope (bucket C, not tested)

- Malformed `subscription_end_date` → treat as no subscription (all status
  fields `null`), do not fail the login.
- `plan_id` pointing to a deleted plan (prevented by `/plans` delete rule).
- Namespace document missing for an existing user → all four fields `null`.
