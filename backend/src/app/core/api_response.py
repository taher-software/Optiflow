from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class ApiResponse(BaseModel, Generic[DataT]):
    """Standard response envelope for every endpoint (per the api skill)."""

    success: bool = True
    message: Optional[str] = None
    data: Optional[DataT] = None
