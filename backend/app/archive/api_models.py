from pydantic import BaseModel


class CreateArchiveRequest(BaseModel):
    server_id: str
    path: str | None = None


class CreateArchiveResponse(BaseModel):
    task_id: str
