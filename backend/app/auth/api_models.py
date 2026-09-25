from pydantic import BaseModel

from app.auth.schemas import UserPublic


class LoginResponse(BaseModel):
    user: UserPublic


class VerifyCodeRequest(BaseModel):
    username: str
    code: str


class VerifyCodeResponse(BaseModel):
    result: str


class CompleteCodeLoginRequest(BaseModel):
    ticket: str
