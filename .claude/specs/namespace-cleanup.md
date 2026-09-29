# BOM — Namespace cleanup (delete a tenant's data)

Feature branch: `feature/namespace-cleanup`.
Status: **DONE** — bucket A ruled on (A1–A3), implemented and reviewed (2026-09-29).
The developer waived the test-first gate for this feature: no test suite is
written first; implementation goes straight to `api-agent`.

## 1. Goal

A back-office endpoint that wipes a namespace (tenant) and every piece of data
it owns in Firestore. Irreversible.

## 2. Data owned by a namespace (inventory)

| Store | Location | Selector |
|---|---|---|
| Namespace | `namespace/{namespace_id}` | doc id |
| Users | `Users/*` | `namespace_id == id` |
| UAPs | `uap/*` | `namespace_id == id` |
| Production lines | `production_line/*` | `namespace_id == id` |
| Workstations | `workstation/*` | `namespace_id == id` |
| Settings | `NamespaceSettings/{id}/settings/{id}` (+ parent doc if present) | path |
| Downtime tickets | `down_time/{id}/issues/*` (+ parent doc if present) | path |

Not namespace-owned, never touched: `plan` (global), `temporary_connection`
(keyed by device, carries no namespace id).

Side effects outside Firestore:
- **Pending Cloud Tasks** (escalation cycles of still-open tickets) are not
  cancelled; when they fire, the escalation handler finds no namespace and
  returns (existing behaviour, `escalate_down_time.py`). To be confirmed by a
  test.
- No Cloud Storage objects and no Firebase Auth accounts exist for a
  namespace today (auth is the backend's own JWT + `Users.password`).

## 3. Endpoint

`DELETE /namespaces/{namespace_id}` — router `src/app/routers/namespace`.

- Auth: `X-API-Key` platform key (`require_api_key`), same as `/plans` and
  `/subscriptions` (A1).
- No request body, no confirmation field (A3).
- Deleted regardless of the namespace's subscription state (A3).
- `404` when the namespace does not exist.
- Deletion runs in Firestore batches (≤ 500 writes each).
- Response `200 ApiResponse[NamespaceCleanupOut]` with per-collection deleted
  counts: `{namespace_id, deleted: {users, uaps, production_lines,
  workstations, issues, settings, namespace}}`.

## 4. Units

| id | owner | produces | depends_on |
|---|---|---|---|
| `contract.bom` | orchestrator | this file | — |
| `gate.triage` | HUMAN | bucket-A answers | done |
| `api.namespace_cleanup` | api | router + services + models (test-first gate waived) | needs contract.bom |
| `doc.namespace_cleanup` | doc | OpenAPI metadata / README section | observes api.namespace_cleanup |
| `review.crosscut` | review | advisory report (tenant isolation focus) | observes api.namespace_cleanup |

## 5. Decisions (bucket A)

- **A1 — back-office only.** `X-API-Key` platform key (`require_api_key`); a
  user bearer token is neither required nor accepted.
- **A2 — full deletion.** Namespace doc, users, UAPs, lines, workstations,
  settings and every downtime ticket are deleted. The tenant disappears and
  its users' emails become free for a new registration.
- **A3 — no extra guard.** No `confirm_namespace_id` body field; an active
  subscription does not block the deletion.
