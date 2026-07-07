# OptiFlow — Mobile Sub-Factory

The mobile sub-factory turns its slice of a feature (its scope + the backend BOM artifacts
it consumes) into working **React Native + TypeScript + TailwindCSS (NativeWind) + Zustand**
UI. It is the mobile twin of the frontend sub-factory — **same logic**, React Native
mechanics.

Like a real factory, **stations run in parallel while each station's work flows in
series**. As with the frontend, **every mobile agent loads the same shared skill**:
`.claude/skills/mobile/SKILL.md` — the mandatory structure, best practices, linter gate,
one-store-per-component data pattern, and data-population verification.

## Proposed roster (5 roles) — ⟨per-agent specs to define next⟩

| Role             | Station (what it owns)                                                | Full spec |
|------------------|----------------------------------------------------------------------|-----------|
| `store-agent`    | Zustand `stores/` — backend data ingestion (typed to the API contract, loading/error). **Primary consumer of the backend BOM.** | ⟨next⟩ |
| `component-agent`| `components/` — small, simple, presentational RN units (+ their `utils/`, `constants/`) | ⟨next⟩ |
| `screen-agent`   | `screens/` (compose components) + `routers/` navigation wiring        | ⟨next⟩ |
| `review-agent`   | Advisory review + linter enforcement against the mobile rubric        | ⟨next⟩ |
| `test-agent`     | Component/screen render + **data-population** tests (RN Testing Library) | ⟨next⟩ |

> Mirrors the frontend roster; `screen-agent` is the mobile analogue of `page-agent`.
> Confirm the roster or dictate each agent's spec and I'll write them into `.claude/agents/`.
>
> **Agent file names (decided):** mobile agents are prefixed `mob-*` to stay globally
> unique — `mob-store-agent`, `mob-component-agent`, `mob-screen-agent`,
> `mob-review-agent`, `mob-test-agent`. (Backend agents keep their unprefixed names;
> frontend uses `fe-*`.) The `owner` enum values stay short and are local to this DAG.

---

## Work Unit — the atomic unit of work

Same schema and rules as the other sub-factories:

```json
{
  "id":          "owner.short_name",          // e.g. "store.report", "screen.report_detail"
  "owner":       "store | component | screen | review | test",
  "description": "what this unit produces",
  "depends_on":  ["other.unit_id", "..."],
  "status":      "pending | queued | in_progress | done | error"
}
```

- Work Units across all mobile agents form one **dependency graph**.
- **Cross-factory dependency:** a data-bound mobile unit `depends_on` the backend BOM
  artifact that produces its data (endpoint + `ApiResponse` schema). The orchestrator only
  marks it ready once that backend artifact is produced **and** has cleared the backend
  firewall — then it hands the contract down as the unit's `inputs`. For a given resource,
  the mobile store mirrors the **same contract shape** the web store uses.
- Typical intra-factory chain: `store.X` (ingests backend data) → `component.X` (renders it)
  → `screen.X` (composes components + navigation) → `test.X` (verifies population).

---

## Agent lifecycle, Singleton Rule, Queue scheduling

Identical to the other sub-factories — see `.claude/factories/backend.md` for the full
definitions. In short:

- **Lifecycle:** `pending → in_progress → idle → suspended → done → error` (orchestrator-tracked labels).
- **Singleton:** exactly ONE logical instance of each role (ONE Store, ONE Component, ONE
  Screen, ONE Review, ONE Test). Parallelism = different roles on different units in the same
  wave; within a role, units run serially via its queue. Never two instances of one role.
- **Queue scheduling:** the orchestrator pushes a unit into its owner's queue once all
  `depends_on` units (and any cross-factory backend artifacts) are `done` and firewall-passed,
  then runs ready units wave by wave.

---

## Quality-at-source — every mobile agent self-inspects

All agents load the shared mobile skill and enforce it as their gates (jidoka):

- **Auto-control (Incoming / IQC):** before building, verify inputs are present and match
  contract. The **`store-agent` in particular** checks the backend API contract (endpoint +
  `ApiResponse` shape) exists and matches before it types the store — if the contract is
  missing or mismatched, **reject back** (`status: "error"`); never fake the data shape.
- **Firewall (Outgoing / OQC):** before hand-off, run the skill's gates — code in the right
  folder, components simple + typed, NativeWind styling, typed navigation params, **`eslint`
  + `tsc --noEmit` + `prettier` clean**, and the **data-population verification** (Section 5
  of the skill) for every data-bound component: correct fetch, correct store selector, all
  four states handled, `FlatList` where applicable, expected fields actually render.
- **`review-agent`** reinforces this advisorily (non-blocking reports); **`test-agent`**
  proves data population with render tests.

---

## Build log

- [x] Mobile sub-factory: shared skill (`.claude/skills/mobile/SKILL.md`),
      coordination model, proposed 5-role roster
- [ ] Next: per-agent specs → `store-agent`, `component-agent`, `screen-agent`,
      `review-agent`, `test-agent` (confirm roster first)
