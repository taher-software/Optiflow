# OptiFlow — Backend Sub-Factory

The backend sub-factory turns its slice of a feature (its scope + owned BOM artifacts,
handed down by the Workload Planner) into working FastAPI + Google Cloud code
(**Firestore** datastore · Pub/Sub · Cloud Tasks · Cloud Run).

Like a real factory, **stations run in parallel while each station's work flows in
series**. It is staffed by five specialized roles:

| Role          | Station (what it owns)                                              | Full spec |
|---------------|--------------------------------------------------------------------|-----------|
| `api-agent`   | FastAPI routers, Pydantic request/response schemas, services        | ✅ `.claude/agents/api-agent.md` |
| `async-agent` | Pub/Sub, Cloud Tasks, background handlers, idempotent workers        | ✅ `.claude/agents/async-agent.md` |
| `doc-agent`   | Human-facing docs + FastAPI OpenAPI metadata (consumes contract files) | ✅ `.claude/agents/doc-agent.md` |
| `review-agent`| Advisory code review (per-component + cross-cutting reports)         | ✅ `.claude/agents/review-agent.md` |
| `test-agent`  | API / async / integration tests (scenario coverage, never model tests) | ✅ `.claude/agents/test-agent.md` |

> This document defines how these five roles are **coordinated**.
>
> **Datastore:** OptiFlow uses **Firestore** (schemaless — no models, no migrations),
> chosen over Postgres for cost. There is **no dedicated DB agent**: Firestore
> reads/writes live inside `api-agent` **services** and `async-agent` **handlers**.
> (db-agent was removed for now; reintroduce a datastore agent only if a relational
> store returns.)

---

## Work Unit — the atomic unit of work

Each agent decomposes its work into Work Units. A Work Unit:

```json
{
  "id":          "owner.short_name",          // e.g. "api.create_refund"
  "owner":       "api | async | doc | review | test",
  "description": "what this unit produces",
  "depends_on":  ["other.unit_id", "..."],
  "status":      "pending | queued | in_progress | done | error"
}
```

- Work Units across all agents form a single **dependency graph**.
- **Synchronization happens at the Work Unit level, not the agent level** — an agent
  can start a ready unit even while another of its units is blocked.

**Relation to the cross-factory BOM:** these are the backend's *internal, fine-grained*
units. A unit whose output is a boundary artifact (an endpoint/schema other
sub-factories depend on) also carries that BOM artifact's `produces` id + `acceptance`
criteria, so the outgoing **firewall** can gate it before it leaves the backend.
⟨Open cleanup: unify this schema with the orchestrator-level Work Unit schema into one
canonical definition — flagged, not yet done.⟩

---

## Agent lifecycle (orchestrator-tracked state per role)

```
pending      → not yet instantiated
in_progress  → instantiated, queue non-empty, actively working
idle         → queue empty, work still to come (transitional)
suspended    → queue empty, awaiting upstream completions
done         → all owned Work Units completed
error        → blocking issue, requires orchestrator intervention
```

In Claude Code these are **labels the orchestrator maintains** about each role's queue —
not a live process. A role in `suspended` simply has no ready unit yet; when an upstream
unit reaches `done`, the orchestrator moves the newly-unblocked unit to `queued` and, on
the next wave, invokes that role's agent to work it (`in_progress`).

---

## Singleton Rule (CRITICAL)

```
Within a single feature pipeline:
  - Exactly ONE logical instance of each specialized agent role
  - ONE API, ONE Async, ONE Doc, ONE Review, ONE Test
  - The queue is the SOLE scheduling mechanism
  - No duplication, no parallel instances of the same role

Parallelism comes from:
  - Different agents working on different Work Units in parallel
  - Work Units within an agent processed SERIALLY via its queue
NEVER from:
  - Multiple instances of the same agent role
```

**Enforcement in Claude Code:** the orchestrator serializes each role's queue — it never
launches two `api.*` (or two of any single role's) units in the same wave. It *may* launch
one `api.*` + one `async.*` + one `test.*` unit together — that is the allowed cross-role
parallelism. Each launch is a fresh one-shot subagent of that role; "singleton" is
guaranteed by the scheduler, not by a resident process.

---

## Queue-based scheduling

- Each agent role has a **queue**, held by the orchestrator.
- The orchestrator **pushes a Work Unit into its owner's queue when all of its
  `depends_on` units are `done`** (and have passed their producing firewall).
- Each wave: for every role, dequeue at most one ready unit → launch those units (one per
  role) in parallel → collect outputs → self-inspection firewall → mark `done`/`error` →
  unblock dependents → repeat until every queue is empty and the DAG has drained.

### Quality-at-source, inside the backend too
Consistent with the factory-wide decision, each backend agent self-inspects:
- **Auto-control (IQC):** before working a unit, verify its `inputs`/upstream artifacts
  are present and match contract; else reject back with a defect report.
- **Firewall (OQC):** before marking `done`, self-review the output against the unit's
  acceptance criteria. `review-agent` and `test-agent` are dedicated reinforcement of
  this gate for backend outputs.

---

## Build log

- [x] Backend sub-factory: roles, Work Unit schema, dependency graph, lifecycle,
      singleton rule, queue scheduling, quality-at-source
- [x] `api-agent` → `.claude/agents/api-agent.md` (skill-driven, IQC/OQC gates)
- [x] `async-agent` → `.claude/agents/async-agent.md` (Pub/Sub, idempotent, backoff×3,
      functional/system failure split, JobType+__init__ registration)
- [x] `doc-agent` → `.claude/agents/doc-agent.md` (human-facing docs, OpenAPI-from-code,
      vocabulary firewall, consumes contract files, anomaly-on-gap)
- [x] `review-agent` → `.claude/agents/review-agent.md` (advisory, non-blocking,
      per-component + cross-cutting, severity rubric + scoring)
- [x] `test-agent` → `.claude/agents/test-agent.md` (API/async/integration scenario
      coverage, factory-boy, mocks Pub/Sub+time, xfail-on-upstream-bug, never edits prod)
- [x] `db-agent` — **REMOVED for now** (Firestore instead of Postgres, cost reasons).
      Firestore data access folded into `api-agent` services + `async-agent` handlers.
      Reintroduce a datastore agent only if a relational store returns.
- ✅ Backend sub-factory complete: **5 agents** (api / async / doc / review / test).
