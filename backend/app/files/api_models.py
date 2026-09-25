from pydantic import BaseModel


class PopulateServerRequest(BaseModel):
    archive_filename: str


class PopulateServerResponse(BaseModel):
    task_id: str
