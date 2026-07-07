# OptiFlow — Backend

**Stack:** FastAPI · Google Cloud (**Firestore** datastore · Pub/Sub · Cloud Tasks · Cloud Run) · Pydantic.
No relational ORM / migrations — Firestore is schemaless.

## Structure
```
src/app/
  routers/        One folder per resource: router + modelsIn + modelsOut + services (see api skill)
  async_jobs/     Background job handlers + __init__.py dispatch mapping (see async skill)
  globals/enum/   Shared enums (e.g. JobType)
  core/           Settings + GCP clients (Firestore, Pub/Sub, Cloud Tasks)
tests/
  api/  async_jobs/  integration/
```

## Governed by
- Sub-factory: `.claude/factories/backend.md`
- Agents: `api-agent`, `async-agent`, `doc-agent`, `review-agent`, `test-agent`
- Skills: `.claude/skills/{api,async,doc,review,test}/SKILL.md`
