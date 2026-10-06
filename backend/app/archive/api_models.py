from typing import Self

from pydantic import BaseModel, Field, model_validator


class CreateArchiveRequest(BaseModel):
    server_id: str
    path: str | None = None
    paths: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.path is not None and self.paths is not None:
            raise ValueError("path 和 paths 不能同时指定")
        return self


class CreateArchiveResponse(BaseModel):
    task_id: str
