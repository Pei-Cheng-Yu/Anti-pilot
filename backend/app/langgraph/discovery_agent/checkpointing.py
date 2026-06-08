from app.core.config import settings

_checkpoint_context = None


def checkpoint_database_url() -> str:
    """Return a psycopg-compatible URL for LangGraph's Postgres checkpointer."""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def create_postgres_checkpointer(*, setup: bool = False):
    """Create and optionally set up the async Postgres checkpointer.

    AsyncPostgresSaver.from_conn_string is an async context manager. Keep that
    context open for the lifetime of the process by storing it in module state.
    """
    global _checkpoint_context

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    _checkpoint_context = AsyncPostgresSaver.from_conn_string(checkpoint_database_url())
    checkpointer = await _checkpoint_context.__aenter__()
    if setup:
        await checkpointer.setup()
    return checkpointer
