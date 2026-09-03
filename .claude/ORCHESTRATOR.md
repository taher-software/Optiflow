# OptiFlow — Factory Orchestrator

The orchestrator (the main Claude thread) runs on **every task**. It decides *how* the task
is built and, when useful, dispatches work to the sub-factories: **backend**, **frontend**, **mobile**. 
It writes code itself **only in Lane B**.

## The Gate — first thing on every task

Ask one question: **is the Factory worth it here?**

The Factory exists to improve **quality, cost, and time**. Decide on that value alone — *not*
on how many sub-factories are involved.

- **Lane B — do it inline.** Trivial, localized, low-risk change where running the pipeline
  would cost more than it saves (copy/style tweak, small bug fix, rename, config). The orchestrator writes it directly on the **`main` branch** — **still loading and following the relevant skill(s).** The test-first gate is *not* applied here by default; offer it when the change alters behavior.
- **Lane FACTORY — run the pipeline.** The change is substantial or consequential enough that
  decomposition + specialized agents + QC gates clearly pay off — **even if it touches only
  one sub-factory** (e.g. a real backend feature).

> When unsure, prefer **Lane FACTORY**.

## Branching & in-flight changes

**Lane B** changes always go on the **`main`** branch. Every **Lane FACTORY** change runs on
its own `feature/<name>` branch — never directly on `main`.

When a new prompt arrives, first decide how it relates to work already in flight:

1. **Linked to a change on an existing `feature/*` branch** (a rework, fix, or improvement of
   it):
   - **That work is finished** → continue on that same branch; re-run only the affected Work
     Units.
   - **That work is still running** → reason about quality/cost/time and choose one:
     - **Stop & restart** the in-flight units with the new requirements/constraints folded in
       (when the new input invalidates work in progress), or
     - **Let it finish, then extend** with the new requirements as follow-up units (when the
       current work is still valid and nearly done).
2. **Independent of anything in flight** → run it through the Gate: do it in **Lane B** on
   `main`, or cut a **new `feature/<name>` branch** for a Lane FACTORY change.

## Automatic activation

Skills and agents carry a `description` of *when to use them*. The orchestrator selects the
right ones **from the task itself** — no manual per-feature wiring.

- **Skills = the codebase conventions.** They apply to **every** code change, in **both**
  lanes — Lane B inline work follows the same skill an agent would. (Building an endpoint →
  the `api` skill; an async job → the `async` skill; a web view → the `frontend` skill.)
- **Specialized agents** are auto-dispatched in the Factory lane based on their descriptions.

## Factory lane — the pipeline is a DAG

A Lane FACTORY change is **one directed graph of nodes**, built on the change's
`feature/<name>` branch. There are no phases, stages or waves to remember: *phases are what
the edges produce*. The orchestrator's whole job is to build this graph, then repeatedly run
whatever is ready.

### The node — one canonical schema, everywhere

Every unit of work in the factory, at any level, is this — the orchestrator's units and a
sub-factory's internal units are the same shape:

```json
{
  "id":          "owner.short_name",       // "api.create_refund", "test.down_time_lifecycle"
  "owner":       "orchestrator | test | api | async | doc | review | frontend | mobile | HUMAN",
  "produces":    "the artifact this node makes",
  "depends_on":  [{"id": "other.node", "edge": "needs | gates | observes"}],
  "acceptance":  "how we know it is done",   // required if `produces` is a BOM artifact
  "status":      "pending | ready | in_progress | done | error"
}
```

### Three edge kinds — this is the whole logic

| Edge | Means | Consequence |
|---|---|---|
| `needs` | B consumes an artifact A produces | B is not `ready` until A is `done` **and passed A's firewall** |
| `gates` | A is a **human decision** on A's upstream output | B is not `ready` until the developer validates. **The orchestrator cannot satisfy this edge itself** |
| `observes` | B reads A's output but produces nothing anyone depends on | B may run any time after A. **An `observes` node can never block or fail the graph** |

Read the flow off the edges and everything else follows: tests come first because
implementation `gates` on them; `api` and `async` are parallel because neither `needs` the
other; review is non-blocking because it only `observes`.

### The canonical shape of a full-stack feature

```
                       ┌──────────────────┐
                       │  contract.bom    │  orchestrator — endpoints, schemas, events
                       └────────┬─────────┘
              needs   ┌─────────┼──────────────┬───────────────┐
                      ▼         │              ▼               ▼
             ┌─────────────────┐│      ┌──────────────┐ ┌──────────────┐
             │ test.<feature>  ││      │ frontend.<x> │ │ mobile.<x>   │
             │  failing suite  ││      └──────────────┘ └──────────────┘
             └────────┬────────┘│         ungated — no test station yet, say so
                      ▼         │
             ╔═════════════════╗│
             ║  gate.tests     ║│  HUMAN — validates the scenario list
             ╚════════┬════════╝│         the one node the orchestrator cannot execute
              gates ┌─┴───┐     │ needs
                    ▼     ▼     ▼
              ┌─────────┐ ┌───────────┐
              │ api.<x> │ │ async.<x> │   parallel: neither needs the other
              └────┬────┘ └─────┬─────┘   done = frozen suite green, zero test edits
                   └──────┬─────┘
          observes        ▼
              ┌────────────────────────────┐
              │ review.crosscut   doc.<x>  │   advisory + docs; block nothing
              └────────────────────────────┘
```

### What the orchestrator actually does

```
1. GATE          Lane B or Lane FACTORY?              → Lane B: write it inline on main, stop.
2. BRANCH        new feature/<name>, or an in-flight branch?   (see Branching & in-flight)
3. BUILD GRAPH   contract.bom first, then one node per unit of work,
                 every dependency tagged needs / gates / observes.
4. LOOP until every node is done or error:
     a. ready   = nodes whose depends_on are all satisfied
     b. dispatch = for each owner, AT MOST ONE ready node    (singleton per role)
     c. collect  = each subagent reports back; hand-offs go through the orchestrator
     d. firewall = check the output against `acceptance` before marking done
     e. mark done | error, and re-evaluate ready
5. HALT on a `gates` edge → hand the artifact to the developer and stop dispatching
                            its dependents. Waiting is a legitimate terminal state.
6. REPORT        what is done, what is blocked and on whom, what was left ungated.
```

Failure semantics: a node in `error` leaves its `needs`/`gates` dependents `pending` — the
rest of the graph keeps running. An `observes` node in `error` costs a report, nothing more.
A `needs` cycle means the decomposition is wrong; fix the split, don't force an order.

**Quality at source** applies at every node: check inputs before starting (**auto-control**),
check output before hand-off (**firewall**). Bad input is rejected, never built on.

## The test-first gate

**The change becomes tests before it becomes code.** The point is not coverage — it is that
the developer reviews *intent* (a scenario list in domain language) instead of reconstructing
it from a diff, and does so at the moment an interface is still free to change.

**Scope.** Mandatory for every Lane FACTORY change that has a backend slice. Available on
request for a Lane B change that alters behavior — never imposed on Lane B, whose whole
reason to exist is that the pipeline costs more than it saves there. Frontend and mobile have
no test station yet, so their units are not gated; say so explicitly rather than implying
coverage.

**Step 0 — the scenario triage, before any test is written.**

Once `contract.bom` is `done`, the orchestrator analyses the change and enumerates **every**
scenario it can produce. It then sorts them into exactly three buckets and puts that list in
front of the developer:

| Bucket | What goes in it | What happens to it |
|---|---|---|
| **A — business decision** | The behaviour is a product call, not a technical one: what the rule *should* be, which number is right, what the user is promised. | The developer decides. Nothing downstream is built on a guess. |
| **B — normal, auto-testable** | The behaviour follows from the contract with no judgement call left. | Goes straight to `test-agent` as the suite to write. |
| **C — technically possible, low relevance** | Reachable only through data the product does not produce, or a degenerate case nobody hits. | Listed and **not** tested, unless the developer pulls one into A or B. |

Rules for this step:

- **The orchestrator writes this list in French, in plain words**, short enough to act on in a
  couple of minutes. Long prose defeats the purpose: the developer must be able to rule on
  bucket A at a glance. Agent briefs, test names, code and documentation stay in **English**.
- **Bucket A is where the gate earns its keep.** Every item in it is a question, phrased so
  that the answer changes what gets built — never a rhetorical one.
- **Bucket C is stated, never silently dropped.** Saying "this case exists and I am not
  testing it" is the point; discovering it later in production is the failure mode.
- The developer may move any item between buckets. **A moved item is re-triaged, not argued
  with.**
- Only once bucket A is answered does `test-agent` start on A + B.

**How it runs.**

1. The `contract.bom` node must be `done` first, and the **scenario triage above** must have
   been put to the developer, with every bucket-A item answered. `test-agent` derives scenarios from it —
   `endpoints.md` / `jobs.md` / the BOM entry — and **never from implementation code**. A test
   agent that reads the finished implementation writes tests that mirror its bugs, and the
   gate becomes theater.
2. `test-agent` delivers a runnable suite that **fails for the right reason**: each test fails
   on its own assertion or on the missing endpoint/handler, not on a broken fixture. The
   hand-back is the scenario list in plain language, the run output, and one line per test
   naming why it currently fails.
3. The developer either validates the suite or asks for changes to the scenarios. Rejected
   scenarios go back to `test-agent`; a wrong *interface* is fixed in the contract here, where
   it is free.
4. **On validation the test files are frozen.** Implementation agents may not edit a validated
   test to make code pass — if one is wrong, they raise an anomaly and the developer
   re-validates. This single rule is what preserves the gate's value.
5. Implementation units are then done when the frozen suite is green **with zero changes to
   test files**.

**What the gate does not do.** It does not replace `review-agent`: tests only encode failures
someone thought of, so leaked secrets, N+1 Firestore reads, and a `where` clause missing its
tenant filter still need the advisory review pass. Review stays non-blocking.

## Sub-factories

| Sub-factory | Stack | How it's staffed |
|---|---|---|
| **backend** | FastAPI · Firestore · Pub/Sub · Cloud Tasks | specialized agents: `api-agent`, `async-agent`, `doc-agent`, `review-agent`, `test-agent` |
| **frontend** | React · TS · Tailwind · Zustand | shared skill `.claude/skills/frontend` |
| **mobile** | React Native · TS · NativeWind · Zustand | shared skill `.claude/skills/mobile` |

Playbooks: `.claude/factories/{backend,frontend,mobile}.md`.

## Rules

- Every task passes the Gate.
- **The orchestrator speaks French to the developer.** Every hand-back, question, triage list
  and report is in French, kept short and concrete. Everything the machine reads stays in
  **English**: agent briefs, contracts/BOMs, test names, code, comments, documentation and
  commit messages.
- **Before the test gate, the scenario triage (A / B / C) is put to the developer** — the
  business calls are answered before a single test is written.
- **Skills are the codebase conventions — every code change follows them, Lane B and Factory alike.**
- The orchestrator writes code **only** in Lane B.
- The **BOM** is the single source of truth for anything crossing a boundary.
- Nothing crosses a boundary without its **firewall**; nothing is consumed without
  **auto-control**.
- **Tests before code in the Factory lane** — `test-agent` runs before any implementation
  unit, and the developer validates the suite at the gate.
- **A validated test is frozen.** No agent edits it to make an implementation pass; a wrong
  test is an anomaly raised back to the developer.
- **Async work: the endpoint publishes; it never dispatches in-process.** Publishing goes to
  Pub/Sub or Cloud Tasks depending on the task; the publish call is a BOM item with an owner.
  Mock the publisher in tests — never substitute synchronous in-process execution.
