from models import User
from sqlmodel import Session, select


def get_user_by_username(session: Session, username: str) -> User | None:
    statement = select(User).where(User.username == username)
    return session.exec(statement).first()


def get_user_by_id(session: Session, user_id: int) -> User | None:
    statement = select(User).where(User.id == user_id)
    return session.exec(statement).first()


def create_user(session: Session, user: User):
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
