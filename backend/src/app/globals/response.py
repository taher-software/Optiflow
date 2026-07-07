from pydantic import BaseModel, SerializeAsAny, model_validator
from typing import Union
from .error import Error
from .status import Status
from typing import Any, Dict
import json


# ================================ Success Api Response =======================================
class ApiResponse(BaseModel):
    status: Status = Status.success
    # SerializeAsAny on the BaseModel arm: a field typed as the bare ``BaseModel``
    # serializes via the base schema (no fields) and collapses any concrete model
    # assigned to it down to ``{}``. ``SerializeAsAny`` makes it serialize the
    # value's *actual* subclass fields instead, so endpoints can pass a model
    # directly and still get a fully-populated ``data`` payload.
    data: float | int | str | list | dict | SerializeAsAny[BaseModel] | None = None
    error: Error | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.data is None:
            delattr(self, "data")
        if self.error is None:
            delattr(self, "error")

    class Config:
        use_enum_values = True

        @staticmethod
        def json_schema_extra(schema, model) -> None:
            if schema.get("properties")["status"]["default"] == "success":
                schema.get("properties").pop("error")
            if schema.get("properties")["status"]["default"] == "failed":
                schema.get("properties").pop("data")
