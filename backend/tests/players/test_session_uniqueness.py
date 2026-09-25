import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.metadata import Base
from app.players.crud.player_session import end_all_open_sessions, get_or_create_session
from app.players.models import PlayerSession


async def test_concurrent_join_counts_one_session_and_repeated_leave_preserves_duration(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    barrier = asyncio.Barrier(2)

    class ConcurrentSession(AsyncSession):
        async def execute(self, statement, *args, **kwargs):
            if not self.info.get("started"):
                self.info["started"] = True
                if statement.is_select:
                    result = await super().execute(statement, *args, **kwargs)
                    await barrier.wait()
                    return result
                # Writers synchronize before acquiring SQLite's transaction lock.
                await barrier.wait()
            return await super().execute(statement, *args, **kwargs)

    factory = async_sessionmaker(engine, class_=ConcurrentSession, expire_on_commit=False)
    joined = datetime(2026, 9, 24, 12, tzinfo=UTC)

    async def join():
        async with factory() as session:
            return (await get_or_create_session(session, 7, 8, joined)).session_id

    try:
        ids = await asyncio.wait_for(asyncio.gather(join(), join()), timeout=5)
        assert len(set(ids)) == 1
        async with AsyncSession(engine, expire_on_commit=False) as session:
            rows = list((await session.execute(select(PlayerSession))).scalars())
            assert len(rows) == 1
            assert rows[0].left_at is None
            assert await end_all_open_sessions(session, 7, 8, joined + timedelta(seconds=60)) == 1
            assert await end_all_open_sessions(session, 7, 8, joined + timedelta(seconds=90)) == 0
            await session.refresh(rows[0])
            assert rows[0].duration_seconds == 60
            assert rows[0].left_at == joined + timedelta(seconds=60)
            next_session = await get_or_create_session(session, 7, 8, joined + timedelta(seconds=120))
            assert next_session.session_id != rows[0].session_id
            assert len(list((await session.execute(select(PlayerSession))).scalars())) == 2
    finally:
        await engine.dispose()


async def test_concurrent_departures_cannot_overwrite_a_recorded_duration(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'departures.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    joined = datetime(2026, 9, 24, 12, tzinfo=UTC)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await get_or_create_session(session, 7, 8, joined)
    observed = asyncio.Barrier(2)
    first_committed = asyncio.Event()

    class DepartureSession(AsyncSession):
        async def execute(self, statement, *args, **kwargs):
            if statement.is_select:
                result = await super().execute(statement, *args, **kwargs)
                await observed.wait()
                if self.info.get("later"):
                    await first_committed.wait()
                return result
            return await super().execute(statement, *args, **kwargs)

    factory = async_sessionmaker(engine, class_=DepartureSession, expire_on_commit=False)

    async def leave(later: bool):
        async with factory(info={"later": later}) as session:
            count = await end_all_open_sessions(session, 7, 8, joined + timedelta(seconds=90 if later else 60))
            if not later:
                first_committed.set()
            return count

    try:
        assert await asyncio.wait_for(asyncio.gather(leave(False), leave(True)), timeout=5) == [1, 0]
        async with AsyncSession(engine) as session:
            row = (await session.execute(select(PlayerSession))).scalar_one()
            assert row.duration_seconds == 60
            assert row.left_at == joined + timedelta(seconds=60)
    finally:
        await engine.dispose()
