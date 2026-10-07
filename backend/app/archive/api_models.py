from datetime import date, time
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator


class CreateArchiveRequest(BaseModel):
    server_id: str
    path: str | None = None
    paths: list[str] | None = Field(default=None, min_length=1)
    client_timestamp: str | None = Field(
        default=None, strict=True, pattern=r"^[0-9]{8}_[0-9]{6}_[0-9]{3}$",
    )

    @field_validator("client_timestamp")
    @classmethod
    def validate_client_timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                date(int(value[:4]), int(value[4:6]), int(value[6:8]))
                time(int(value[9:11]), int(value[11:13]), int(value[13:15]), int(value[16:]) * 1000)
            except ValueError as error:
                raise ValueError("浏览器本地时间必须是有效的年月日、时分秒和毫秒") from error
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.path is not None and self.paths is not None:
            raise ValueError("path 和 paths 不能同时指定")
        return self


class CreateArchiveResponse(BaseModel):
    task_id: str
