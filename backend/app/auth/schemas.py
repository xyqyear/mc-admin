from datetime import datetime

from pydantic import BaseModel
from pydantic import Field as PydanticField

from app.auth.models import UserRole


class UserBase(BaseModel):
    username: str
    role: UserRole = UserRole.ADMIN


class UserPublic(UserBase):
    id: int
    created_at: datetime


class UserCreate(BaseModel):
    username: str = PydanticField(min_length=3, max_length=50)
    password: str
    role: UserRole = UserRole.ADMIN
