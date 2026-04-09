from contextlib import asynccontextmanager

from app.core.config import settings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = settings.database_url

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
