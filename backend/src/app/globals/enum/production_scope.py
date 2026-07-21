from enum import Enum


class ProductionScope(str, Enum):
    """Granularity level at which a downtime issue is declared/scoped."""

    PLANT = "plant"
    UAP = "uap"
    PRODUCTION_LINE = "production line"
    WORK_STATION = "work station"
