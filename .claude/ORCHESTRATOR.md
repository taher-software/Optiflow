# OptiFlow — Factory Orchestrator

The orchestrator (the main Claude thread) runs on **every task**. It decides *how* the task
is built and, when useful, dispatches work to the sub-factories: **backend**, **frontend**, **mobile**. 
It writes code itself **only in Lane B**.

## The Gate — first thing on every task

Ask one question: **is the Factory worth it here?**

The Factory exists to improve **quality, cost, and time**. Decide on that value alone — *not*
on how many sub-factories are involved.

- **Lane B — do it inline.** Trivial, localized, low-risk change where running the pipeline
  would cost more than it saves (copy/style tweak, small bug fix, rename, config). The orchestrator writes it directly on the **`main` branch** — **still loading and following the relevant skill(s).**
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

## Factory lane

1. **Intent** — work on the change's `feature/<name>` branch (see **Branching & in-flight
   changes** for which branch a new prompt belongs to).
2. **Contract (BOM)** — list every artifact that crosses a sub-factory boundary (REST
   endpoints + their schemas, Pub/Sub events, shared TS types), one owner each. Single source
   of truth.
3. **Work Units** — each sub-factory splits its scope into small units. A unit states what it
   `produces` and what it `depends_on` (possibly from another sub-factory).
4. **Waves** — run every unit whose dependencies are ready; collect results; unblock the next
   wave; repeat. Sub-factories are subagents that report back, so hand-offs go through the
   orchestrator.
5. **Quality at source** — each sub-factory checks its inputs before starting
   (**auto-control**) and its output before hand-off (**firewall**). Bad input is rejected,
   never built on.

## Sub-factories

| Sub-factory | Stack | How it's staffed |
|---|---|---|
| **backend** | FastAPI · Firestore · Pub/Sub · Cloud Tasks | specialized agents: `api-agent`, `async-agent`, `doc-agent`, `review-agent`, `test-agent` |
| **frontend** | React · TS · Tailwind · Zustand | shared skill `.claude/skills/frontend` |
| **mobile** | React Native · TS · NativeWind · Zustand | shared skill `.claude/skills/mobile` |

Playbooks: `.claude/factories/{backend,frontend,mobile}.md`.

## Rules

- Every task passes the Gate.
- **Skills are the codebase conventions — every code change follows them, Lane B and Factory alike.**
- The orchestrator writes code **only** in Lane B.
- The **BOM** is the single source of truth for anything crossing a boundary.
- Nothing crosses a boundary without its **firewall**; nothing is consumed without
  **auto-control**.
- **Async work: the endpoint publishes; it never dispatches in-process.** Publishing goes to
  Pub/Sub or Cloud Tasks depending on the task; the publish call is a BOM item with an owner.
  Mock the publisher in tests — never substitute synchronous in-process execution.
