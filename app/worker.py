from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.orders import service as order_service

# Регистрируем модели, чтобы SQLAlchemy-реестр был полным (как в main.py)
import app.models  # noqa: F401


async def cancel_expired_orders_task(ctx) -> None:
    """Cron-задача: отменяет просроченные неоплаченные заказы."""
    async with AsyncSessionLocal() as db:
        count = await order_service.cancel_expired_orders(db, max_age_minutes=15)
        if count:
            print(f"[worker] Отменено просроченных заказов: {count}")


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    # Запускать каждую минуту (на каждой 0-й секунде)
    cron_jobs = [cron(cancel_expired_orders_task, second=0)]