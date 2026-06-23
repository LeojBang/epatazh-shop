import asyncio

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.orders import service as order_service
from app.core.email import send_email


# Регистрируем модели, чтобы SQLAlchemy-реестр был полным (как в main.py)
import app.models  # noqa: F401


async def send_email_task(ctx, to: str, subject: str, body: str) -> None:
    """Фоновая задача отправки письма (не блокирует основное приложение)."""
    # send_email синхронный (smtplib) — выполняем в отдельном потоке,
    # чтобы не блокировать event loop воркера
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, send_email, to, subject, body)


async def cancel_expired_orders_task(ctx) -> None:
    """Cron-задача: отменяет просроченные неоплаченные заказы."""
    async with AsyncSessionLocal() as db:
        count = await order_service.cancel_expired_orders(db, max_age_minutes=15)
        if count:
            print(f"[worker] Отменено просроченных заказов: {count}")


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    functions = [send_email_task]  # задачи, которые можно ставить в очередь
    cron_jobs = [cron(cancel_expired_orders_task, second=0)]
