from contextlib import contextmanager

from asyncer import asyncify
from config import settings
from models import SQLModel
from sqlmodel import Session, create_engine

engine = create_engine(settings.database_url, echo=True)


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session


@asyncify
def init_db():
    SQLModel.metadata.create_all(engine)
