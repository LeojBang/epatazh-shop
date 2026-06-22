import redis.asyncio as redis
from fastapi.requests import Request

MAX_ATTEMPTS = 5  # сколько неудач разрешаем
WINDOW_SECONDS = 15 * 60  # за какое время (15 минут)
BLOCK_SECONDS = 15 * 60  # на сколько блокируем после превышения

# Регистрация: ограничиваем создание аккаунтов с одного IP (анти-спам)
REGISTER_MAX = 10  # сколько регистраций с одного IP
REGISTER_WINDOW_SECONDS = 60 * 60  # за час


def _key(ip: str, action: str = "login") -> str:
    return f"{action}_attempts:{ip}"


async def is_blocked(
    r: redis.Redis, ip: str, action: str = "login", max_attempts: int = MAX_ATTEMPTS
) -> bool:
    """Проверяет, заблокирован ли IP за превышение попыток."""
    value = await r.get(_key(ip, action))
    if value is None:
        return False
    return int(value) >= max_attempts


async def register_failed_attempt(r: redis.Redis, ip: str) -> int:
    """Увеличивает счётчик неудачных попыток входа. Возвращает текущее число."""
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


async def register_attempt(
    r: redis.Redis,
    ip: str,
    action: str,
    window_seconds: int,
) -> int:
    """Считает попытку действия `action` с IP в скользящем окне. Возвращает счётчик.

    В отличие от логина, здесь считаем КАЖДУЮ попытку (а не только неудачную)
    и не продлеваем окно — это анти-спам по объёму, а не блокировка перебора.
    """
    key = _key(ip, action)
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window_seconds)
    return count


def get_client_ip(request: Request) -> str:
    """Возвращает IP посетителя.

    За nginx реальный адрес приходит в заголовке X-Forwarded-For.
    ВАЖНО: nginx с `proxy_add_x_forwarded_for` ДОПИСЫВАЕТ настоящий адрес
    клиента в КОНЕЦ цепочки, не очищая то, что прислал клиент. Поэтому брать
    первый элемент нельзя — его может подделать клиент и обойти rate-limit.
    Берём последний элемент (его проставил наш доверенный nginx).

    Если за приложением несколько прокси — увеличьте TRUSTED_PROXY_HOPS
    и берите соответствующий элемент с конца.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            # Последний адрес добавил наш nginx — ему доверяем.
            return parts[-1]
    # Запасной вариант: прямое подключение (разработка без nginx)
    return request.client.host if request.client else "unknown"
