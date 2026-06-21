import asyncio
from decimal import Decimal

from sqlalchemy import select, func

from app.core.database import AsyncSessionLocal
from app.models.catalog import Category, Product, ProductVariant


# Минимальный стартовый каталог — категории без товаров,
# товары владелец добавит через админку
CATEGORIES = [
    ("ММА", "mma"),
    ("Муай-тай", "muay-thai"),
    ("Хоккей", "hockey"),
]


async def seed_prod():
    async with AsyncSessionLocal() as db:
        # Проверяем, есть ли уже категории — если да, ничего не делаем
        count = await db.scalar(select(func.count()).select_from(Category))
        if count and count > 0:
            print(f"Каталог уже содержит {count} категорий. Пропускаем.")
            return

        for name, slug in CATEGORIES:
            db.add(Category(name=name, slug=slug))
        await db.commit()
        print(f"Создано категорий: {len(CATEGORIES)}. Товары добавьте через админку.")


if __name__ == "__main__":
    asyncio.run(seed_prod())