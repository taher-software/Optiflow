"""Shared exception types async job handlers use to classify failures.

Per the async skill, a handler must distinguish:
- `FunctionalJobError`: the input is invalid or a business condition isn't
  met — logged and NOT retried.
- `SystemJobError`: an external system is down or the error is transient —
  retried with backoff up to `dispatch_job`'s `MAX_RETRIES`, then logged and
  swallowed.

Any other (unclassified) exception raised by a handler is treated by
`dispatch_job` as a system failure (retried then given up on), so handlers
only need to raise these explicitly when they want to force a specific path
(e.g. a functional short-circuit).
"""


class FunctionalJobError(Exception):
    """Raised when a job's input is invalid or a business rule blocks it.

    `dispatch_job` logs this and skips further retries.
    """


class SystemJobError(Exception):
    """Raised when a job fails due to a transient / external system issue.

    `dispatch_job` retries this with backoff, up to `MAX_RETRIES` attempts.
    """
