---
name: async-job
description: async job design base for this code base
context: fork
disable-model-invocation: false
---

# Async jobs

Flow: **endpoint publishes → worker route receives the push → registry routes to the
handler.** The endpoint and the handler are coupled ONLY through the published message.
Never run a handler in-process from an endpoint, and never hand-roll a retry loop.

## Trigger — in the endpoint
Publish the job; do not run it. Never import a handler or a dispatcher into an endpoint.
The publisher depends on the task: use `get_pubsub_publisher().publish_job(...)` for a
**Pub/Sub** job, or the Cloud Tasks caller for a **Cloud Task** job.
```py
get_pubsub_publisher().publish_job(JobType.X, namespace_id, payload, job_id)  # Pub/Sub
```

## Worker route — the ONLY entrypoints that run jobs
Two routes, one shared registry lookup — **neither has app auth, infra OIDC only** — and
**both always return HTTP 200**, never a non-2xx, which would make the broker requeue a
message forever:

- `POST /cloud_job` — **Cloud Tasks only.** Body is the flat shape Cloud Tasks delivers:
  `{job_id, job_type, namespace_id, payload}`.
- `POST /pubsub_job` — **Pub/Sub push only.** Body is the push subscription envelope
  (`{message: {data: <base64 JSON>, messageId, publishTime, attributes}, subscription}`);
  the route base64-decodes `message.data`, reads `{job_id, job_type, namespace_id, payload}`
  from the root of that decoded JSON, and delegates to the exact same lookup as
  `/cloud_job`. Any envelope that cannot be turned into a valid job (missing/invalid `data`,
  bad base64, invalid JSON, unknown `job_type`, no `message` at all, ...) is **logged at
  `error` and still acked 200** — it is never rejected with a 4xx/5xx.

Do not send a Pub/Sub push to `/cloud_job` (its flat body won't match the envelope and it
will 422, which is a redelivery loop) or a Cloud Tasks body to `/pubsub_job`. Whichever route
receives the call, it looks the handler up in the registry by `job_type` and **returns the
handler's response**. There is **no manual `dispatch_job`/retry orchestrator**: the registry
in `src/app/async_jobs/__init__.py` is a plain `dict[JobType, handler]`.

## Handler — one file per job in `src/app/async_jobs/`
1. New job → new file `src/app/async_jobs/<job>.py`; add its value to the `JobType` enum
   (`src/app/globals/enum`) and register `JobType.X -> handler` in `async_jobs/__init__.py`.
2. **Retry = the `backoff` decorator — never a hand-rolled loop / `time.sleep`, and never a
   `giveup` predicate.** Add `backoff` to `requirements.txt`. Wrap the handler body in
   `try/except`:
   - `FunctionalJobError` (invalid input / business rule) → **log and return OK** (no retry).
   - any other (system / external API / transient) failure → let it propagate; the decorator
     retries with backoff up to `max_tries=3`; on exhaustion `on_giveup` logs and the handler
     returns OK to the broker (never requeue what cannot succeed).
   ```py
   @backoff.on_exception(
       backoff.expo, Exception, max_tries=3,
       on_giveup=_log_giveup, raise_on_giveup=False,
   )
   def my_job(namespace_id, payload, job_id):
       try:
           ...  # raise FunctionalJobError for bad input; let transient errors propagate
           return {"status": "ok"}
       except FunctionalJobError as e:
           logger.warning(...); return {"status": "skipped", "reason": str(e)}
   ```
3. **Idempotent** — delivery is at-least-once; replaying the same `job_id` must cause no
   duplicate side effects (e.g. use `job_id` as the document id and short-circuit if it
   already exists).
