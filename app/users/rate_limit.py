import redis.asyncio as redis

MAX_ATTEMPTS = 5  # сколько неудач разрешаем
WINDOW_SECONDS = 15 * 60  # за какое время (15 минут)
BLOCK_SECONDS = 15 * 60  # на сколько блокируем после превышения


def _key(ip: str) -> str:
    return f"login_attempts:{ip}"


async def is_blocked(r: redis.Redis, ip: str) -> bool:
    """Проверяет, заблокирован ли IP за превышение попыток."""
    value = await r.get(_key(ip))
    if value is None:
        return False
    return int(value) >= MAX_ATTEMPTS


async def register_failed_attempt(r: redis.Redis, ip: str) -> int:
    """Увеличивает счётчик неудачных попыток. Возвращает текущее число."""
    key = _key(ip)
    count = await r.incr(key)
    if count == 1:
        # первый промах — ставим время жизни ключа
        await r.expire(key, WINDOW_SECONDS)
    if count >= MAX_ATTEMPTS:
        # достигли лимита — продлеваем блокировку
        await r.expire(key, BLOCK_SECONDS)
    return count


async def reset_attempts(r: redis.Redis, ip: str) -> None:
    """Сбрасывает счётчик (при успешном входе)."""
    await r.delete(_key(ip))
