# OptiFlow — Backend

**Stack:** FastAPI · Google Cloud (**Firestore** datastore · Pub/Sub · Cloud Tasks · Cloud Run) · Pydantic.
No relational ORM / migrations — Firestore is schemaless.

## Structure
```
src/app/
  routers/        One folder per resource: __init__.py (endpoints) + modelsIn + modelsOut + services (see api skill)
  async_jobs/     Background job handlers + __init__.py dispatch mapping (see async skill)
  globals/enum/   Shared enums (e.g. JobType)
  core/           Settings + GCP clients (Firestore, Pub/Sub, Cloud Tasks)
tests/
  api/  async_jobs/  integration/
```

## Environment & tests

```bash
cd backend
python3 -m venv .venv                          # first time only
.venv/bin/pip install -r requirements-dev.txt  # runtime + test dependencies
.venv/bin/python -m pytest -q                  # run the suite
```

`requirements-dev.txt` pulls in `requirements.txt`, so that single install gives
an environment able to run both the app and the tests.

**Always run the suite through the venv's interpreter** (`.venv/bin/python -m
pytest`, or `source .venv/bin/activate` first). A bare `pytest` resolves through
`PATH` and may pick up a user- or system-wide install running on the system
Python, which has none of the project's dependencies — it fails with
`ModuleNotFoundError` (e.g. `itsdangerous`) that looks like a missing
requirement but is really the wrong interpreter.

## Governed by
- Sub-factory: `.claude/factories/backend.md`
- Agents: `api-agent`, `async-agent`, `doc-agent`, `review-agent`, `test-agent`
- Skills: `.claude/skills/{api,async,doc,review,test}/SKILL.md`
