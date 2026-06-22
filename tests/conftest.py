import pytest_asyncio
import fakeredis.aioredis
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base


@pytest_asyncio.fixture
async def db_session():
    """Создаёт чистую тестовую БД (SQLite в памяти) для каждого теста."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Создаём все таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Отдаём сессию тесту
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session

    # После теста — закрываем
    await engine.dispose()


@pytest_asyncio.fixture
async def fake_redis():
    """Поддельный Redis в памяти для тестов корзины."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.flushall()
    await r.aclose()
