# OptiFlow — Backend Sub-Factory

The backend sub-factory turns its slice of a feature (its scope + owned BOM artifacts,
handed down by the Workload Planner) into working FastAPI + Google Cloud code
(**Firestore** datastore · Pub/Sub · Cloud Tasks · Cloud Run).

The five roles are **not five parallel peers**. Each role's own units run in series, and
two roles run together only when no edge separates them. Read the backend's slice of the
graph (see *The pipeline is a DAG* in `.claude/ORCHESTRATOR.md` for the node schema and the
three edge kinds) and the shape falls out on its own:

```
  contract ──needs──▶ test.<f> ──▶ ║gate.tests║ ──gates──┬──▶ api.<f>   ─┐
                                    (HUMAN)              └──▶ async.<f> ─┤
                                                                        │
                       doc.<f> ◀──needs──────────────────────────────────┤
                       review.crosscut ◀──observes───────────────────────┘
```

- `test.<f>` is alone before the gate — nothing may be built beside the suite that specifies it.
- `api.<f>` ∥ `async.<f>` is the **only** genuine build parallelism: different layers, no edge between them.
- `doc.<f>` ∥ `review.crosscut` close the change; neither is on anyone's critical path.

It is staffed by five specialized roles:

| Role          | Station (what it owns)                                              | Full spec |
|---------------|--------------------------------------------------------------------|-----------|
| `api-agent`   | FastAPI routers, Pydantic request/response schemas, services        | ✅ `.claude/agents/api-agent.md` |
| `async-agent` | Pub/Sub, Cloud Tasks, background handlers, idempotent workers        | ✅ `.claude/agents/async-agent.md` |
| `doc-agent`   | Human-facing docs + FastAPI OpenAPI metadata (consumes contract files) | ✅ `.claude/agents/doc-agent.md` |
| `review-agent`| Advisory code review (per-component + cross-cutting reports)         | ✅ `.claude/agents/review-agent.md` |
| `test-agent`  | API / async / integration tests (scenario coverage, never model tests) | ✅ `.claude/agents/test-agent.md` |

> This document defines how these five roles are **coordinated** inside that graph.
>
> **Datastore:** OptiFlow uses **Firestore** (schemaless — no models, no migrations),
> chosen over Postgres for cost. There is **no dedicated DB agent**: Firestore
> reads/writes live inside `api-agent` **services** and `async-agent` **handlers**.
> (db-agent was removed for now; reintroduce a datastore agent only if a relational
> store returns.)

---

## Work Unit — the atomic unit of work

A backend Work Unit is a **node in the orchestrator's graph** — same schema, no backend
variant: see *The node — one canonical schema, everywhere* in `.claude/ORCHESTRATOR.md`
(`id` · `owner` · `produces` · `depends_on[{id, edge}]` · `acceptance` · `status`).
Backend units simply have `owner` in `api | async | doc | review | test`.

- Backend units are the *fine-grained* nodes; they sit in the same single graph as every
  other sub-factory's, so a `depends_on` may point outside the backend.
- **Synchronization happens per node, not per role** — a role can start a ready unit while
  another of its units is blocked.
- A unit whose `produces` is a **boundary artifact** (an endpoint/schema another
  sub-factory consumes) carries that BOM artifact's id and `acceptance` criteria, so the
  outgoing **firewall** can gate it before it leaves the backend.

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
  - Different roles working nodes that NO edge separates
  - Work Units within a role processed SERIALLY via its queue
NEVER from:
  - Multiple instances of the same agent role
  - Nodes separated by a `needs` or `gates` edge
```

**Enforcement in Claude Code:** the orchestrator serializes each role's queue — it never
launches two `api.*` (or two of any single role's) units in the same wave. Beyond that, the
edge decides, never the role:

| Together? | Nodes | Edge between them |
|---|---|---|
| ✅ | `api.<f>` + `async.<f>` | none — different layers of the same feature |
| ✅ | `doc.<f>` + `review.crosscut` | none — one `needs` the code, the other `observes` it |
| ❌ | `test.<f>` + the `api.<f>`/`async.<f>` it covers | `gates` — the suite and its human validation are upstream |
| ✅ | `test.<g>` + `api.<f>` (different features) | none — independent branches of the graph |

So `test-agent` is not a parallel peer of the build stations *for its own feature*, and is
perfectly parallel with them across features. Each launch is a fresh one-shot subagent of
that role; "singleton" is guaranteed by the scheduler, not by a resident process.

---

## Queue-based scheduling

- Each agent role has a **queue**, held by the orchestrator.
- The orchestrator **pushes a Work Unit into its owner's queue when all of its
  `depends_on` units are `done`** (and have passed their producing firewall).
- Each wave: for every role, dequeue at most one ready unit → launch those units (one per
  role) in parallel → collect outputs → self-inspection firewall → mark `done`/`error` →
  unblock dependents → repeat until every queue is empty and the DAG has drained.
- **Nobody sequences the roles by hand.** Implementation `gates` on a validated `test.*`,
  and `doc.*`/`review.*` sit downstream of implementation — so spec → build → close is
  simply what those edges produce. A single wave holding all five roles of one feature
  means the graph is wrong, not that the line is fast.

### Test-first ordering (the human gate)

The `test.*` units for a feature run **before** its `api.*` / `async.*` units, not after —
see **The test-first gate** in `.claude/ORCHESTRATOR.md`. Consequences for scheduling:

- A `test.*` unit `depends_on` the **contract** (`endpoints.md` / `jobs.md` / the BOM entry),
  never on the `api.*` / `async.*` unit it covers.
- Every implementation unit carries a **`gates` edge** on the `gate.tests` node — the
  developer's validation of that suite. It is the one edge the orchestrator cannot satisfy
  itself: it never dequeues the implementation unit on the developer's behalf.
- The suite handed to the gate is expected to be **red**, failing on its own assertions or on
  the missing endpoint/handler. Red-for-the-wrong-reason (broken fixture, import error) is a
  firewall failure on the `test.*` unit.
- After validation the test files are **frozen inputs** for the implementation unit. An
  implementation agent that wants a validated test changed reports `status: "error"` with the
  anomaly instead of editing it.
- `review-agent` still runs afterwards — the gate does not replace it (tests only encode
  failures someone thought of; see below for where it sits).

### Where `review-agent` sits

**Default: end of the line, as the closing firewall.** Once every `api.*` / `async.*` unit is
`done` and the frozen suite is green, `review-agent` runs its **cross-cutting** pass over the
whole change. That is the placement worth preferring — it is the only point where consistency
*across* units is visible, and it produces one report to read during final review instead of
several partial ones.

**Per-component review in parallel is also fine.** `review-agent` may instead (or in addition)
review a single unit's output as soon as it lands, in the same wave as the next unit's build.
It is advisory and never edits code, so it creates no write conflict and blocks nothing.

Either way review is **non-blocking**: findings are severity-rated reports for the developer,
never a gate that stops the pipeline.

### Quality-at-source, inside the backend too
Consistent with the factory-wide decision, each backend agent self-inspects:
- **Auto-control (IQC):** before working a unit, verify its `inputs`/upstream artifacts
  are present and match contract; else reject back with a defect report.
- **Firewall (OQC):** before marking `done`, self-review the output against the unit's
  acceptance criteria.

The two dedicated reinforcements sit at **opposite ends** of the line, not side by side:
`test-agent` is the **upstream** gate (the contract becomes an executable, human-validated
spec before anything is built), `review-agent` is the **downstream** one (advisory findings
once it is built).

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
- ✅ Backend sub-factory complete: **5 agents** (api / async / doc / review / test),
      scheduled off one shared DAG (`needs` / `gates` / `observes`) around the
      test-first human gate.
