import asyncio
import os

from sqlalchemy import text

from app.core.database import AsyncSessionLocal


async def clean_orders():
    # Защита от запуска на проде
    if os.getenv("ENVIRONMENT") == "production":
        print("ОТКАЗ: скрипт удаляет данные и запрещён на production.")
        return

    async with AsyncSessionLocal() as db:
        # Удаляем в порядке зависимостей:
        # сначала то, что ссылается на заказы, потом сами заказы.
        # Товары, категории, пользователей НЕ трогаем.
        await db.execute(text("DELETE FROM return_requests"))
        await db.execute(text("DELETE FROM payments"))
        await db.execute(text("DELETE FROM order_items"))
        await db.execute(text("DELETE FROM orders"))
        await db.commit()
        print("Удалены: заказы, позиции заказов, платежи, заявки на возврат.")
        print("Товары, категории и пользователи сохранены.")


if __name__ == "__main__":
    asyncio.run(clean_orders())
