import argparse

from db.crud.user import create_user, get_user_by_username
from db.database import SQLModel, engine, get_session
from jwt_utils import get_password_hash
from logger import logger
from models import User, UserCreate, UserRole


def register(user: UserCreate) -> User:
    with get_session() as session:
        db_user = get_user_by_username(session, user.username)
        if db_user is not None:
            logger.error(f"Username {user.username} already registered")
            raise ValueError("Username already registered")

        hashed_password = get_password_hash(user.password)
        new_user = User.model_validate(
            user, update={"hashed_password": hashed_password}
        )
        create_user(session, new_user)

        return new_user


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    # Register subcommand
    register_parser = subparsers.add_parser("register")
    register_parser.add_argument("--username", type=str, required=True)
    register_parser.add_argument("--password", type=str, required=True)
    register_parser.add_argument("--role", type=UserRole, default="admin")

    args = parser.parse_args()

    if args.command == "register":
        SQLModel.metadata.create_all(engine)
        user = register(UserCreate(username=args.username, password=args.password))
        logger.info(f"User {user.username} created with id {user.id}")


if __name__ == "__main__":
    main()
