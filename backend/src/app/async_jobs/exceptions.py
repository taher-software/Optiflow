"""Shared exception types async job handlers use to classify failures
(see `.claude/skills/async`).

A handler wraps its body in `try/except`:
- `FunctionalJobError` (invalid input / business rule) → caught, logged, and
  the handler returns OK — NOT retried.
- any other exception (incl. `SystemJobError`) → propagates to the handler's
  `backoff` decorator, which retries up to 3 attempts; on exhaustion its
  `on_giveup` logs and the handler returns OK to the broker.
"""


class FunctionalJobError(Exception):
    """Raised when a job's input is invalid or a business rule blocks it.

    Caught by the handler's `try/except`, logged, and acked (no retry).
    """


class SystemJobError(Exception):
    """Raised when a job fails due to a transient / external system issue.

    Propagates to the handler's `backoff` decorator and is retried (up to 3).
    """
