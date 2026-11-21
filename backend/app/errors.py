from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field


class FieldError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    message: str


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    fields: list[FieldError] = Field(default_factory=list)


@dataclass
class CompatibilityError(Exception):
    status_code: int
    code: str
    message: str
    fields: tuple[FieldError, ...] = ()
