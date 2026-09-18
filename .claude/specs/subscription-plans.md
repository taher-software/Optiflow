# BOM — Subscription plans + namespace subscriptions

Feature branch: `feature/subscription-plans`.
Status: **VALIDATED** — bucket A ruled on by the developer (2026-09-18).
The developer waived the test-first gate for this feature: no test suite is
written; implementation goes straight to `api-agent`.

## 1. Goal

Platform-level (back-office) management of commercial plans and of which plan a
namespace (tenant) is subscribed to. These endpoints are **not** called by tenant
users: they are protected by a platform API key, not by a user bearer token.

## 2. Auth — platform API key

| Item | Value |
|---|---|
| Header | `X-API-Key` |
| Setting | `platform_api_key: str = ""` in `core/config.py` (env `PLATFORM_API_KEY`) |
| Dependency | `require_api_key` in `core/deps.py` |
| Comparison | `hmac.compare_digest` (constant time) |
| Missing / wrong key | `401` `"Invalid or missing API key."` |
| Setting empty | every request rejected with `401` (fail closed) |

Applies to **every** endpoint of §4 and §5. A user bearer token is neither
required nor accepted as a substitute.

## 3. Namespace — new fields at registration

`registration.services.create_account` writes seven extra fields on the new
namespace document, all `null`:

```jsonc
{ "subscription_plan_id": null, "subscription_start_date": null,
  "subscription_end_date": null, "oiu_generated": null,
  "extra_subscription_plan_id": null, "extra_subscription_start_date": null,
  "extra_subscription_end_date": null }
```

- Dates are stored as ISO `YYYY-MM-DD` strings (calendar dates, no time).
- Namespaces registered before this change have no such keys: every reader
  treats a missing key exactly like `null`. No backfill.

## 4. Plans — `/plans` (CRUD)

Router `src/app/routers/plan`, collection `PLAN_COLLECTION = "plan"` (global,
not tenant-scoped).

### 4.1 Schema

| Field | Type | Required | Rule |
|---|---|---|---|
| `name` | str | yes | trimmed, non-blank; unique across plans, case-insensitive |
| `price` | float | yes | `>= 0`, a plain number, no currency |
| `duration` | int | yes | number of days, `>= 1` |
| `quota` | int \| null | no | `>= 0` when present; default `null` |

`PlanOut` = `{id, name, price, duration, quota}`.

### 4.2 Endpoints

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| POST | `/plans` | `CreatePlanIn` (all fields of 4.1) | `201` `PlanOut` | `409` name taken · `422` validation |
| GET | `/plans` | — | `200` `list[PlanOut]` sorted by `name` | — |
| GET | `/plans/{plan_id}` | — | `200` `PlanOut` | `404` |
| PATCH | `/plans/{plan_id}` | `UpdatePlanIn` (every field optional; `quota` may be set to `null`) | `200` `PlanOut` | `404` · `409` name taken by another plan · `422` |
| DELETE | `/plans/{plan_id}` | — | `200` `PlanOut` (the deleted plan) | `404` · `409` plan in use |

A plan is **in use** when any namespace has `subscription_plan_id == plan.id`
or `extra_subscription_plan_id == plan.id`. A plan in use is never deleted.

All responses wrapped in `ApiResponse[...]`. Editing a plan never touches
namespaces already subscribed to it (their dates/quota stay as computed).

## 5. Subscriptions — `/subscriptions`

Router `src/app/routers/subscription`.

### 5.1 `POST /subscriptions`

Body `CreateSubscriptionIn`:

| Field | Type | Required |
|---|---|---|
| `namespace_id` | str | yes, non-blank |
| `plan_name` | str | yes, must match an existing plan (same case-insensitive, trimmed match as §4.1) |
| `today_start_day` | bool | no, default `false` |

There are two kinds of subscription, chosen by the plan:

- **Base subscription** — `plan.quota` is `null`. Touches only
  `subscription_plan_id`, `subscription_start_date`, `subscription_end_date`.
  `oiu_generated` and every `extra_*` field stay unchanged.
- **Extra (quota) subscription** — `plan.quota` is not `null`. Touches only
  `extra_subscription_plan_id`, `extra_subscription_start_date`,
  `extra_subscription_end_date` and `oiu_generated`. The base
  `subscription_*` fields stay unchanged.

Let `P` be the prefix of the touched fields (`subscription_` or
`extra_subscription_`). "today" = the current date in the namespace timezone
(fallback UTC). Logic, one `update_document` call on the namespace:

1. `P plan_id` ← plan `id`.
2. `P start_date` ← **today** if `today_start_day` is `true` **or** the current
   `P end_date` is `null`/missing; otherwise current `P end_date + 1 day`
   (applied literally, even if that date is in the past).
3. `P end_date` ← `P start_date + plan.duration` days.
4. Extra subscription only — `oiu_generated`, evaluated against the
   **previous** `extra_subscription_end_date` (before step 2/3):
   - previous `extra_subscription_end_date` not null **and** `> today` (extra
     subscription still active) →
     `oiu_generated ← (current oiu_generated or 0) + plan.quota` (added to the
     remaining balance);
   - otherwise (null, or `<= today`) → `oiu_generated ← plan.quota` (replaced).

Response `201` `ApiResponse[SubscriptionOut]`:

```jsonc
{ "namespace_id": "...", "plan_id": "...", "plan_name": "Pro",
  "is_extra": true,
  "subscription_plan_id": "...", "subscription_start_date": "2026-09-18",
  "subscription_end_date": "2026-10-18",
  "extra_subscription_plan_id": "...", "extra_subscription_start_date": "2026-09-18",
  "extra_subscription_end_date": "2026-10-18",
  "oiu_generated": 500 }
// the namespace's full subscription state after the update
```

| Error | When |
|---|---|
| `401` | API key missing / wrong |
| `404` | `namespace_id` does not exist |
| `422` | `plan_name` matches no plan · validation errors |

No subscription history is stored; the namespace fields are the whole state.
