from enum import Enum

from .down_time_type import DownTimeType


class Process(str, Enum):
    """Plant department/process a downtime ticket is routed to."""

    PRODUCTION = "production"
    MAINTENANCE = "maintenance"
    QUALITY = "quality"
    LOGISTIC = "logistic"


# Maps each DownTimeType to the process/department that owns it.
#
# `SETUP_CHANGEOVER` is intentionally NOT included here: its process is not
# fixed — it's chosen from a department at runtime when the ticket is
# declared.
DOWNTIME_TYPE_PROCESS: dict[DownTimeType, Process] = {
    DownTimeType.BREAKDOWN: Process.MAINTENANCE,
    DownTimeType.QUALITY_ISSUE: Process.QUALITY,
    DownTimeType.ABSENTEEISM: Process.PRODUCTION,
    DownTimeType.WIP_SHORTAGE: Process.PRODUCTION,
    DownTimeType.MATERIAL_SHORTAGE: Process.LOGISTIC,
    DownTimeType.OTHERS: Process.PRODUCTION,
}


# Downtime types that skip the acknowledge/resolve steps entirely and go
# straight `pending -> closed`. No responder "repairs" these in the OptiFlow
# sense: a production agent simply confirms production has resumed, so there
# is no diagnosis/repair phase to acknowledge or resolve. Note both types here
# route to `Process.PRODUCTION` above, so the notified agents are the same
# production agents who close the ticket.
#
# `MATERIAL_SHORTAGE` is deliberately NOT close-only: it routes to
# `Process.LOGISTIC`, and the logistic agent does acknowledge and resolve it
# (they physically supply the missing parts), before production closes it.
#
# Consumers: the down_time router's permission flags + lifecycle transitions,
# and the notification variant table in `src.app.core.notifications`.
CLOSE_ONLY_DOWNTIME_TYPES: frozenset[DownTimeType] = frozenset(
    {DownTimeType.OTHERS, DownTimeType.WIP_SHORTAGE}
)
