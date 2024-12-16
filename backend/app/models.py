from enum import Enum

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlmodel import Field, SQLModel


class UserRole(str, Enum):
    ADMIN = "admin"
    OWNER = "owner"


class UserBase(SQLModel):
    username: str = Field(unique=True, index=True)
    role: UserRole = Field(default=UserRole.ADMIN)


class User(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str


class UserPublic(UserBase):
    id: int


class UserCreate(BaseModel):
    # we need pydantic field to add validation
    username: str = PydanticField(min_length=3, max_length=50)
    password: str
