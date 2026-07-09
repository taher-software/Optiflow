# OptiFlow — Factory Orchestrator

The orchestrator (the main Claude thread) runs on **every task**. It decides *how* the task
is built and, when useful, dispatches work to the sub-factories: **backend**, **frontend**,
**mobile**. It writes code itself **only in Lane B**.

## The Gate — first thing on every task

Ask one question: **is the Factory worth it here?**

The Factory exists to improve **quality, cost, and time**. Decide on that value alone — *not*
on how many sub-factories are involved.

- **Lane B — do it inline.** Trivial, localized, low-risk change where running the pipeline
  would cost more than it saves (copy/style tweak, small bug fix, rename, config). The
  orchestrator writes it directly on the current branch — **still loading and following the
  relevant skill(s).**
- **Lane FACTORY — run the pipeline.** The change is substantial or consequential enough that
  decomposition + specialized agents + QC gates clearly pay off — **even if it touches only
  one sub-factory** (e.g. a real backend feature).

> When unsure, prefer **Lane FACTORY**.

## Automatic activation

Skills and agents carry a `description` of *when to use them*. The orchestrator selects the
right ones **from the task itself** — no manual per-feature wiring.

- **Skills = the codebase conventions.** They apply to **every** code change, in **both**
  lanes — Lane B inline work follows the same skill an agent would. (Building an endpoint →
  the `api` skill; an async job → the `async` skill; a web view → the `frontend` skill.)
- **Specialized agents** are auto-dispatched in the Factory lane based on their descriptions.

## Factory lane

1. **Intent** — new capability → cut `feature/<name>`; reworking in-flight work → stay on its
   `feature/*` branch and re-run only the affected units.
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
