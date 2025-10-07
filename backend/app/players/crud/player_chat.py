"""CRUD operations for PlayerChatMessage model."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ...models import PlayerChatMessage


async def create_chat_message(
    session: AsyncSession,
    player_db_id: int,
    server_db_id: int,
    message_text: str,
    sent_at: datetime,
) -> None:
    """Create a chat message record.

    Args:
        session: Database session
        player_db_id: Player database ID
        server_db_id: Server database ID
        message_text: Message content
        sent_at: Message timestamp
    """
    chat_message = PlayerChatMessage(
        player_db_id=player_db_id,
        server_db_id=server_db_id,
        message_text=message_text,
        sent_at=sent_at,
    )
    session.add(chat_message)
    await session.commit()
