# OptiFlow — Main Orchestrator

> The Factory is the **main process for EVERY task**, no matter how small.
> This document governs how the orchestrator (the main Claude Code thread) handles
> any incoming request before anything else happens.

## Role

The orchestrator is the **conductor**. It dispatches jobs across three specialized
sub-factories:

- **backend** — FastAPI · Google Cloud: **Firestore** (datastore) · Pub/Sub · Cloud Tasks · Cloud Run
- **frontend** — React · TypeScript · TailwindCSS · Zustand
- **mobile** — React Native · TypeScript · TailwindCSS · Zustand

With **one exception** (Lane B, below), the orchestrator itself **never writes code**.

---

## The Gate — first action on every task (binary)

On receiving any task, make a single binary decision:

### Lane B — Small task
A localized change to **existing** code that does NOT warrant the multi-factory
pipeline.

- The orchestrator **writes the code itself**.
- Directly on the **original branch** (normally `main`).
- Handled **sequentially, do-it-now**.
- **This is the only lane where the orchestrator authors code.**

### Lane FACTORY — Everything else
Falls through to **Step 0 — Intent Detection** (below). In this lane the
orchestrator acts as **conductor only**:

1. Detect intent (Step 0).
2. Optionally plan.
3. Instantiate the **Workload Planner**.
4. Manage **Work Units** and **sub-factory lifecycle**.

> **In the Factory lane the orchestrator never writes code.**

**Gate criteria (Lane B vs Factory):** ⟨TO DEFINE — Step 1a⟩
The precise, testable rule that separates "localized change to existing code" from
"everything else." Needs concrete heuristics (files touched, layers spanned,
new-surface vs. edit, etc.).

---

## Step 0 — Intent Detection  (Factory lane only)

Classifies the task into one of:

- **NEW_FEATURE** → *start* a new pipeline.
  - Cut a new `feature/*` branch.
- **LIGHT_REWORK** → *continue / rework* an in-flight pipeline.
  - Operate on the existing `feature/*` branch.

Detailed classification heuristics: ⟨TO DEFINE — Step 2⟩

---

## Factory-lane execution model (the production line)

Runs when the Gate routes to Lane FACTORY and Step 0 has classified intent.
The orchestrator owns lifecycle only — never code.

### 1. Workload Planner → shared interface contract (the BOM)
- Splits the feature across the three sub-factories, scoping each one.
- Defines the cross-factory **interface contract** — the manufacturing **Bill of
  Materials**: every artifact that crosses a sub-factory boundary, each with exactly
  one owning factory. For OptiFlow that means:
  - REST endpoints + their Pydantic request/response schemas,
  - Pub/Sub event shapes / Cloud Tasks payloads,
  - shared TypeScript types the clients consume.
- The BOM is the **single source of truth** that every sub-factory decomposes against.

### 2. Each sub-factory decomposes its scope into Work Units
Each sub-factory breaks its assigned scope into Work Units. Every unit declares its
dependencies — which may be produced by another sub-factory.

**Work Unit schema**
```
id:          <factory>-<n>            e.g. backend-1, frontend-2
factory:     backend | frontend | mobile
title:       short imperative
produces:    [BOM artifact ids this unit outputs]     e.g. [GET /reports/{id}, ReportSchema]
depends_on:  [BOM artifact ids / work-unit ids required before this unit may start]
inputs:      upstream artifacts to ingest (contracts, schemas, shared types)
acceptance:  done-criteria the outgoing firewall inspects against
```

### 3. Dependency graph & parallel, dependency-gated scheduling
- The orchestrator merges every sub-factory's Work Units into one **global DAG** keyed
  on BOM artifacts.
- Units with no unmet dependency run **in parallel** (launched together).
- A unit becomes **ready** only when every `depends_on` artifact is **(a) produced**
  **and (b) cleared the producing factory's firewall**.
- Example: `frontend-2` (*new page*) depends on `backend-1` (*`GET /reports/{id}` +
  `ReportSchema`*). The orchestrator runs `backend-1` first; once the endpoint + schema
  clear the backend firewall, `frontend-2` becomes ready and starts, ingesting
  `ReportSchema` to consume and render the data.

> **Claude Code reality (how "parallel + dependency-gated" is actually executed):**
> sub-factories are subagents that return a final report to the orchestrator — they
> cannot message each other directly and cannot idle-wait mid-run. So the orchestrator
> implements the model as **waves**: launch all currently-ready units together, collect
> and gate their outputs, route the produced artifacts into the briefs of newly-ready
> downstream units, and repeat until the DAG drains. The conceptual model is unchanged;
> every hand-off is simply **mediated by the orchestrator** instead of going
> factory-to-factory.

### 4. Quality gates — two inspection stations per sub-factory
Every sub-factory sits between two QC stations, like a real production line:

- **Auto-control (Incoming / IQC)** — *before starting* a Work Unit, the sub-factory
  validates the received brief and every upstream artifact it depends on: are the
  contracts/schemas present, complete, and matching the BOM? If not → **reject back**
  to the orchestrator with a precise defect report. Never build on bad input.
- **Firewall (Outgoing / OQC)** — *before handing any output* downstream, the
  sub-factory reviews that output against the unit's `acceptance` criteria and the BOM
  contract. Only conforming artifacts pass the firewall and become available to
  dependent units.

**QC ownership (decided): quality-at-source / self-inspection.** Each sub-factory
performs *both* gates itself — no separate inspector agent. Auto-control and firewall
are built into every sub-factory's own protocol (jidoka): it inspects what it receives
before starting and inspects what it produces before hand-off.

---

## Invariants

- The Factory runs for **every** task; nothing bypasses the Gate.
- Orchestrator authors code **only** in Lane B.
- Factory-lane work happens on `feature/*` branches; Lane B on the original branch.
- The **BOM is the single source of truth** for every cross-factory artifact.
- Nothing **crosses a boundary** without passing the producing factory's **firewall**.
- Nothing is **consumed** without passing the receiving factory's **auto-control**.
- A Work Unit starts only when all `depends_on` artifacts are produced **and** gated.
- Sub-factories: **backend**, **frontend**, **mobile**.
- **Agent naming:** backend agents are unprefixed (`api-agent`, `review-agent`, …);
  frontend agents are `fe-*`; mobile agents are `mob-*` — so `name:` stays globally unique.

---

## Open questions (need your call)

1. **Gate criteria** (Lane B vs Factory) — still ⟨TO DEFINE — Step 1a⟩.
2. **Step 0 intent heuristics** (NEW_FEATURE vs LIGHT_REWORK) — still ⟨TO DEFINE — Step 2a⟩.
3. ~~QC ownership~~ — **decided: quality-at-source (self-inspection).**

---

## Build log (which steps are defined)

- [x] Step 1 — Orchestrator role + binary Gate + Lane FACTORY skeleton
- [x] Step 2 — Factory-lane execution: BOM, Work Unit schema, dependency DAG,
      parallel/wave scheduling, IQC auto-control + OQC firewall gates
- [ ] Step 1a — Gate criteria (Lane B vs Factory)
- [ ] Step 2a — Step 0 Intent Detection heuristics
- [x] Step 3a — QC ownership decided: quality-at-source (self-inspection)
- [x] Step 3b — Backend sub-factory internals → `.claude/factories/backend.md`
- [x] Step 3c — Backend agents (api / async / doc / review / test); db-agent removed (Firestore)
- [x] Step 4 — Frontend sub-factory internals + shared skill → `.claude/factories/frontend.md`,
      `.claude/skills/frontend/SKILL.md` (roster proposed; per-agent specs pending)
- [ ] Step 4a — Frontend per-agent specs (store / component / page / review / test)
- [x] Step 5 — Mobile sub-factory internals + shared skill → `.claude/factories/mobile.md`,
      `.claude/skills/mobile/SKILL.md` (roster proposed; per-agent specs pending)
- [ ] Step 5a — Mobile per-agent specs (store / component / screen / review / test)
