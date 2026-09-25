from datetime import UTC, datetime

from sqlalchemy import TEXT, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TZDatetime


class SystemHeartbeat(Base):
    """Single-row table whose timestamp is bumped on each heartbeat for crash detection."""

    __tablename__ = "system_heartbeat"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    timestamp: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )


class Player(Base):
    __tablename__ = "player"

    player_db_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    current_name: Mapped[str] = mapped_column(String(16))
    skin_data: Mapped[bytes | None] = mapped_column()
    avatar_data: Mapped[bytes | None] = mapped_column()
    last_skin_update: Mapped[datetime | None] = mapped_column(TZDatetime())
    created_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )


class PlayerSession(Base):
    __tablename__ = "player_session"
    __table_args__ = (
        Index(
            "uq_player_session_open",
            "player_db_id",
            "server_db_id",
            unique=True,
            sqlite_where=text("left_at IS NULL"),
            postgresql_where=text("left_at IS NULL"),
        ),
        Index("idx_player_session_player_time", "player_db_id", "joined_at"),
        Index("idx_player_session_server_time", "server_db_id", "joined_at"),
        Index("idx_player_session_server_online", "server_db_id", "left_at"),
        Index(
            "idx_player_session_player_server_online",
            "player_db_id",
            "server_db_id",
            "left_at",
        ),
        Index("idx_player_session_player_left_at", "player_db_id", "left_at"),
    )

    session_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_db_id: Mapped[int] = mapped_column(Integer, index=True)
    server_db_id: Mapped[int] = mapped_column(Integer, index=True)
    joined_at: Mapped[datetime] = mapped_column(TZDatetime())
    left_at: Mapped[datetime | None] = mapped_column(TZDatetime())
    duration_seconds: Mapped[int | None] = mapped_column(Integer)


class PlayerChatMessage(Base):
    __tablename__ = "player_chat_message"
    __table_args__ = (
        Index("idx_player_chat_player_time", "player_db_id", "sent_at"),
        Index("idx_player_chat_server_time", "server_db_id", "sent_at"),
        {"sqlite_autoincrement": True},
    )

    message_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_db_id: Mapped[int] = mapped_column(Integer, index=True)
    server_db_id: Mapped[int] = mapped_column(Integer, index=True)
    message_text: Mapped[str] = mapped_column(TEXT)
    sent_at: Mapped[datetime] = mapped_column(TZDatetime())


class PlayerAchievement(Base):
    __tablename__ = "player_achievement"
    __table_args__ = (
        Index(
            "idx_player_achievement_unique",
            "player_db_id",
            "server_db_id",
            "achievement_name",
            unique=True,
        ),
        Index("idx_player_achievement_time", "earned_at"),
        Index("idx_player_achievement_player_time", "player_db_id", "earned_at"),
        Index("idx_player_achievement_server_time", "server_db_id", "earned_at"),
    )

    achievement_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_db_id: Mapped[int] = mapped_column(Integer, index=True)
    server_db_id: Mapped[int] = mapped_column(Integer, index=True)
    achievement_name: Mapped[str] = mapped_column(String(255))
    earned_at: Mapped[datetime] = mapped_column(TZDatetime())
