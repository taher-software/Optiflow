# BOM — Subscription paywall (web)

Feature branch: `feature/subscription-paywall`.
Status: **VALIDATED** — bucket A ruled on by the developer (2026-09-18).
The developer waived the test-first gate for this feature.
Scope: **backend** (one read endpoint) + **web frontend**. Mobile is out of scope.

Depends on: `.claude/specs/subscription-plans.md`,
`.claude/specs/login-subscription-status.md`.

## 1. Backend — `GET /subscriptions/plans`

Tenant-facing plan catalog, read by the web paywall.

| Item | Value |
|---|---|
| Router | `src/app/routers/subscription` |
| Auth | user bearer token via `core.deps.get_current_user`, **any role**. NOT the platform API key. |
| Response | `200` `ApiResponse[list[CatalogPlanOut]]` |
| Errors | `401` missing/invalid bearer token |

The router today carries `dependencies=[Depends(require_api_key)]` at router
level. Move that dependency onto the existing `POST /subscriptions` route
itself so the platform-key protection of `POST` is unchanged and the new `GET`
is bearer-protected only.

Returns **only** the plans whose name matches (same trimmed, case-insensitive
comparison as `core.naming.normalized_name`) one of the catalog names below,
in this order; any catalog name with no matching plan is simply absent:

1. `Operio Standard`
2. `Operio Dedicated`
3. `Operio Intelligence`

`CatalogPlanOut` = `{id, name, price, duration, quota, maintenance_price}`
(same types as `PlanOut`; `quota` / `maintenance_price` nullable).

No subscription status in this response: status comes only from the login
response (developer decision — no refresh endpoint).

## 2. Frontend (web) — subscription state

### 2.1 Auth store

`useAuthStore` keeps, from the login response root, and persists alongside the
token: `warning: boolean | null`, `blocked: boolean | null`,
`planId: string | null`, `planName: string | null`. Cleared on sign-out.
A session persisted before this change (fields absent) is treated as
not warned / not blocked.

### 2.2 Behaviour

| Login state | Behaviour |
|---|---|
| `blocked === true` | Every `/app/*` route except the subscription page redirects to the subscription page. Sidebar navigation to other pages is not possible (hide or disable those links). Sign-out, language switcher and public legal pages (`/privacy`, `/terms`) remain available. |
| `warning === true` | Free navigation. A persistent warning banner on every `/app/*` page: subscription expired, renew as soon as possible to avoid the system being blocked; with a "Renew" link to the subscription page. |
| otherwise | Nothing displayed. The subscription page is not reachable (redirect to `/app`), and no sidebar entry. |

New route `ROUTES.subscription = "/app/subscription"`, inside the protected
`AppLayout`.

### 2.3 Which plans the subscription page shows

Plans come from `GET /subscriptions/plans`, matched by **backend name**:

| Backend name | Display name | Kind |
|---|---|---|
| `Operio Standard` | Operio Standard | base |
| `Operio Dedicated` | Operio Private | base |
| `Operio Intelligence` | Operio Intelligence | complementary (quota) |

- `planId === null` (never subscribed) → **all** catalog plans, as a
  **first purchase**. Operio Intelligence is shown with the note "in
  addition to a base plan".
- `planId !== null` → **only** the plan whose `id === planId`, as a
  **renewal**.

### 2.4 Amounts (all plan prices are HT, currency TND)

HT amount per plan:

| Plan | First purchase | Renewal |
|---|---|---|
| Operio Standard | `price` | `price` |
| Operio Dedicated (Private) | `price + maintenance_price` (acquisition + first year maintenance & hosting) | `maintenance_price` |
| Operio Intelligence | `price` | `price` |

A missing `maintenance_price` counts as `0`.

Breakdown shown on each plan, every figure visible to the customer:

- Montant HT = HT
- TVA 19 % = HT × 0.19
- Timbre fiscal = 1.000 TND (once per transfer)
- **Total TTC = HT + TVA + 1.000**

Rounded to 3 decimals (millimes), formatted per locale with the `TND`
currency. Compute in integer millimes to avoid float drift.

Duration: `duration` is in days; `365` displays as "annual" / "per year",
otherwise "N days". Operio Intelligence also shows its `quota` as the maximum
number of requests. Operio Private shows the acquisition price and the annual
maintenance & hosting price separately, above the breakdown.

### 2.5 Plan features (static copy, i18n fr + en)

- **Operio Standard** — deployment on Azibodin infrastructure; standard
  application; product updates; storage/hosting included; standard support.
- **Operio Private** — the customer buys a dedicated installation, not just a
  licence. Dedicated infrastructure for the company; specific deployment;
  identity customisation (logo, colours, domain name); configuration adapted to
  how the plant operates; possibility of specific developments.
- **Operio Intelligence** — complementary plan that lets the plant start
  querying its own data; works with a quota = maximum number of requests.

### 2.6 Payment instructions (bank transfer)

Shown on the subscription page:

- Account holder: `AZIBODIN`
- RIB: `08032012041002057880`
- Bank: `Biat Agence El Bouhaira C4`

Guide the user: transfer the Total TTC of the chosen plan to this account;
the subscription is activated after the transfer is received. No payment
reference is requested (developer decision).

### 2.7 i18n

Every user-facing string in `src/i18n/locales/fr.ts` and `en.ts`. Bank details
live in `src/constants/`.

## 3. Out of scope

- Mobile app.
- Backend enforcement of `blocked` (the API keeps serving; UI-only block).
- Status refresh without re-login.
- Online payment.
