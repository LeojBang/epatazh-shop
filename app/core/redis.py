import redis.asyncio as redis

from app.core.config import settings

redis_pool = redis.ConnectionPool.from_url(settings.REDIS_URL)

# Общий клиент поверх пула — переиспользуем вместо создания нового на каждый запрос.
redis_client = redis.Redis(connection_pool=redis_pool)


async def get_redis() -> redis.Redis:
    return redis_client
