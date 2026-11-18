import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import get_settings
from app.models.entities import Base


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        # Free hosting runs migrations during startup. Serialize overlapping
        # deploys with a session-level PostgreSQL lock, released on disconnect.
        await connection.execute(text("SELECT pg_advisory_lock(73002648)"))
        await connection.commit()
        try:
            await connection.run_sync(migrate)
        finally:
            await connection.execute(text("SELECT pg_advisory_unlock(73002648)"))
            await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url, target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
