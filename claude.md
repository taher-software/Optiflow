# OptiFlow

## What it is
OptiFlow is a **multi-tenant SaaS** that helps manufacturing plants manage **machine
downtime** efficiently. When a workstation stops for any reason, OptiFlow drives a workflow
that tracks the incident from detection all the way to a validated return to production, and
feeds plant **KPIs** with the data collected along the way.

Each plant / organization is a **tenant** with strictly isolated data.

## Core domain workflow — the downtime lifecycle
When a workstation goes down for any specific reason, a **downtime workflow** is triggered
and followed until resolution:

1. **Detection** — a workstation stops working; a downtime **ticket** is opened.
2. **Notify** — the proper **responders** (the responsible maintenance technicians/team for
   that station) are notified of the issue.
3. **Acknowledge** — a responder acknowledges the ticket (starts the response clock).
4. **Track** — responders **continuously update the ticket** (status, cause, actions taken)
   through diagnosis and repair. The ticket always reflects the current state.
5. **Resolve & validate** — the fix is applied and **production is validated** as back to
   normal; the ticket is closed only after that validation.
6. **KPI feed** — every event and timestamp along the way feeds the plant's KPIs.

## Multi-tenancy
- **Tenant = a plant / organization.** All data (workstations, tickets, responders, KPIs) is
  scoped and isolated per tenant.
- Tenant scoping / isolation mechanism in Firestore: `⟨TBD — confirm the model⟩`.

## KPIs (fed by the downtime lifecycle)
Key plant metrics derived from ticket + downtime data. Typical set (confirm the exact list):
- **MTTR** (mean time to repair), **MTBF** (mean time between failures)
- **Downtime duration**, **availability / OEE**
- Tickets by **cause / line / shift / station**, acknowledge & resolution SLA adherence

`⟨TBD — confirm the authoritative KPI list and definitions.⟩`

## Domain glossary (disambiguation)
> **Two different meanings of "agent" live in this repo — do not conflate them.**
- **Responder** (a.k.a. maintenance *agent* in the product domain) = a **human** technician /
  responsible user who acknowledges and resolves downtime tickets. This is a product concept.
- **Workstation / machine** = the monitored production asset that can go down.
- **Downtime ticket** = the tracked incident record, from detection to validated resolution.
- **Tenant** = a plant / organization using OptiFlow.
- **KPI** = a plant performance metric fed by downtime events.
- **AI dev agents / "the factory"** (`.claude/`) = the internal AI orchestration that *builds*
  OptiFlow. Entirely separate from product "responders". Never let build-system vocabulary
  (agent, queue, orchestrator, factory, pipeline…) leak into user-facing product docs.

---

## Stack
### Backend
FastAPI + Google Cloud (**Firestore** datastore · Pub/Sub · Cloud Tasks · Cloud Run) + Pydantic.
Firestore is schemaless — no relational ORM / migrations. (Moved off SQLAlchemy/PostgreSQL for
cost; see `.claude/factories/backend.md`.) Pub/Sub + Cloud Tasks drive downtime notifications
and workflow steps.
### Frontend (web)
React + TypeScript + TailwindCSS + Zustand (state management).
### Mobile
React Native + TypeScript + TailwindCSS (NativeWind) + Zustand (state management).

## Repository layout
```
backend/    FastAPI + Firestore service        (see backend/README.md)
frontend/   React web app                       (see frontend/README.md)
mobile/     React Native app                    (see mobile/README.md)
.claude/    The AI dev factory that builds all three (orchestrator, sub-factories, agents, skills)
```

## How work gets built
All development runs through the orchestrator defined in `.claude/ORCHESTRATOR.md`: every task
passes a binary Gate (small change vs. full multi-factory pipeline), and feature work is
decomposed into Work Units dispatched across the **backend / frontend / mobile** sub-factories.
