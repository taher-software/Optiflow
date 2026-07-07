# OptiFlow — Frontend Sub-Factory

The frontend sub-factory turns its slice of a feature (its scope + the backend BOM
artifacts it consumes) into working **React + TypeScript + TailwindCSS + Zustand** UI.

Like a real factory, **stations run in parallel while each station's work flows in
series**. Unlike the backend (one skill per agent), **every frontend agent loads the same
shared skill**: `.claude/skills/frontend/SKILL.md` — the mandatory structure, best
practices, linter gate, one-store-per-component data pattern, and data-population
verification.

## Proposed roster (5 roles) — ⟨per-agent specs to define next⟩

| Role             | Station (what it owns)                                                | Full spec |
|------------------|----------------------------------------------------------------------|-----------|
| `store-agent`    | Zustand `stores/` — backend data ingestion (typed to the API contract, loading/error). **Primary consumer of the backend BOM.** | ⟨next⟩ |
| `component-agent`| `components/` — small, simple, presentational units (+ their `utils/`, `constants/`) | ⟨next⟩ |
| `page-agent`     | `pages/` (compose components) + `routers/` route wiring               | ⟨next⟩ |
| `review-agent`   | Advisory review + linter enforcement against the frontend rubric      | ⟨next⟩ |
| `test-agent`     | Component render + **data-population** tests                          | ⟨next⟩ |

> This is a proposal aligned to the structure you gave. Confirm the roster or dictate each
> agent's spec (same as the backend agents) and I'll write them into `.claude/agents/`.
>
> **Agent file names (decided):** frontend agents are prefixed `fe-*` to stay globally
> unique — `fe-store-agent`, `fe-component-agent`, `fe-page-agent`, `fe-review-agent`,
> `fe-test-agent`. (Backend agents keep their unprefixed names; mobile uses `mob-*`.)
> The `owner` enum values below stay short (`store | component | page | review | test`)
> since they are local to this factory's DAG.

---

## Work Unit — the atomic unit of work

Same schema and rules as the backend sub-factory:

```json
{
  "id":          "owner.short_name",          // e.g. "store.report", "component.report_card"
  "owner":       "store | component | page | review | test",
  "description": "what this unit produces",
  "depends_on":  ["other.unit_id", "..."],
  "status":      "pending | queued | in_progress | done | error"
}
```

- Work Units across all frontend agents form one **dependency graph**.
- **Cross-factory dependency:** a data-bound frontend unit `depends_on` the backend BOM
  artifact that produces its data (endpoint + `ApiResponse` schema). The orchestrator only
  marks it ready once that backend artifact is produced **and** has cleared the backend
  firewall — then it hands the contract down as the unit's `inputs`.
- Typical intra-factory chain: `store.X` (ingests backend data) → `component.X` (renders it)
  → `page.X` (composes components + route) → `test.X` (verifies population).

---

## Agent lifecycle, Singleton Rule, Queue scheduling

Identical to the backend sub-factory — see `.claude/factories/backend.md` for the full
definitions. In short:

- **Lifecycle:** `pending → in_progress → idle → suspended → done → error` (orchestrator-tracked labels).
- **Singleton:** exactly ONE logical instance of each role (ONE Store, ONE Component, ONE
  Page, ONE Review, ONE Test). Parallelism = different roles on different units in the same
  wave; within a role, units run serially via its queue. Never two instances of one role.
- **Queue scheduling:** the orchestrator pushes a unit into its owner's queue once all
  `depends_on` units (and any cross-factory backend artifacts) are `done` and firewall-passed,
  then runs ready units wave by wave.

---

## Quality-at-source — every frontend agent self-inspects

All agents load the shared frontend skill and enforce it as their gates (jidoka):

- **Auto-control (Incoming / IQC):** before building, verify inputs are present and match
  contract. The **`store-agent` in particular** checks the backend API contract (endpoint +
  `ApiResponse` shape) exists and matches before it types the store — if the contract is
  missing or mismatched, **reject back** (`status: "error"`); never fake the data shape.
- **Firewall (Outgoing / OQC):** before hand-off, run the skill's gates — code in the right
  folder, components simple + typed, Tailwind styling, **`eslint` + `tsc --noEmit` +
  `prettier` clean**, and the **data-population verification** (Section 5 of the skill) for
  every data-bound component: correct fetch, correct store selector, all four states
  handled, expected fields actually render.
- **`review-agent`** reinforces this advisorily (non-blocking reports); **`test-agent`**
  proves data population with render tests.

---

## Build log

- [x] Frontend sub-factory: shared skill (`.claude/skills/frontend/SKILL.md`),
      coordination model, proposed 5-role roster
- [ ] Next: per-agent specs → `store-agent`, `component-agent`, `page-agent`,
      `review-agent`, `test-agent` (confirm roster first)
