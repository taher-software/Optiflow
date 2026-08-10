"""Single shared namespace-timezone resolver.

Both the sync API layer (`routers/down_time/services.py`) and the async job
layer (`async_jobs/_common.py`) need to resolve a namespace's IANA timezone
the same way — `core/` is the neutral home either side may import without
crossing the sync/async boundary. There must be exactly one implementation;
every caller that needs it imports this one.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def namespace_timezone(
    namespace_id: str, namespace: Optional[dict[str, Any]]
) -> ZoneInfo:
    """Resolve the namespace's IANA timezone, defaulting to UTC when missing,
    blank, or unknown."""
    tz_name = (namespace or {}).get("timezone") or "UTC"
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning(
            f"namespace_timezone: unknown timezone '{tz_name}' for namespace "
            f"'{namespace_id}', defaulting to UTC."
        )
        return ZoneInfo("UTC")
