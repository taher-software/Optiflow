---
name: endpoint-structure
description: endpoint design pattern for this code base
context: fork
disable-model-invocation: false
---

# Endpoint structure

Each resource gets a router **folder**. Everything for that resource lives in that folder,
and the endpoints are declared in the folder's **`__init__.py`** — do NOT create a separate
router/endpoint file.

Files in the router folder:
- **`__init__.py`** — the `APIRouter` and its endpoint(s). This is where routes are defined.
- **`modelsIn`** — all request/input base models.
- **`modelsOut`** — all response base models. Every endpoint's `response_model` is `ApiResponse`.
- **`services`** — the endpoint's business logic.

Rules for every endpoint:
1. Rich documentation (summary, description, error `responses`).
2. Response model is always `ApiResponse`.
3. Treat the endpoint as a single **atomic transaction**: any failure must trigger a complete
   rollback of everything it did — datastore writes and any resources created during
   execution, whenever possible. The endpoint either completes fully or leaves the system
   unchanged.
4. A self-service route acting on the caller's own resource (e.g. `/{resource}/me/...`) must
   be declared in `__init__.py` **before** any `/{resource}/{id}...` route on the same
   resource, otherwise the path parameter greedily captures the literal `me` segment.
