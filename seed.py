import asyncio
from decimal import Decimal

from sqlalchemy import delete, text

from app.core.database import AsyncSessionLocal
from app.models.catalog import Category, Product, ProductVariant, ProductImage


# Каждый товар: (название, slug, описание, цена, [(размер, остаток), ...])
DATA = {
    "ММА": {
        "slug": "mma",
        "products": [
            (
                "Рашгард MMA Fighter",
                "rashgard-mma-fighter",
                "Компрессионный рашгард с коротким рукавом для тренировок и спаррингов.",
                Decimal("2890.00"),
                [("S", 8), ("M", 12), ("L", 10), ("XL", 5)],
            ),
            (
                "Шорты ММА Grappling",
                "shorts-mma-grappling",
                "Лёгкие шорты для грэпплинга с эластичными вставками.",
                Decimal("2490.00"),
                [("S", 6), ("M", 9), ("L", 7), ("XL", 4)],
            ),
            (
                "Футболка ММА Team",
                "tshirt-mma-team",
                "Хлопковая футболка с принтом, для повседневной носки и зала.",
                Decimal("1590.00"),
                [("S", 15), ("M", 20), ("L", 18), ("XL", 10)],
            ),
            (
                "Худи ММА Champion",
                "hoodie-mma-champion",
                "Тёплое худи с капюшоном, плотный хлопок с начёсом.",
                Decimal("3990.00"),
                [("S", 5), ("M", 8), ("L", 6), ("XL", 3)],
            ),
        ],
    },
    "Муай-тай": {
        "slug": "muay-thai",
        "products": [
            (
                "Шорты Muay Thai Patriot",
                "shorts-muay-thai-patriot",
                "Классические тайские шорты с широкой резинкой и яркой сублимацией.",
                Decimal("2790.00"),
                [("S", 10), ("M", 14), ("L", 11), ("XL", 6)],
            ),
            (
                "Рашгард Muay Thai Warrior",
                "rashgard-muay-thai-warrior",
                "Рашгард с длинным рукавом, дышащая ткань для интенсивных тренировок.",
                Decimal("3190.00"),
                [("S", 7), ("M", 10), ("L", 9), ("XL", 4)],
            ),
            (
                "Футболка Muay Thai Fighter",
                "tshirt-muay-thai-fighter",
                "Футболка с тематическим принтом тайского бокса.",
                Decimal("1690.00"),
                [("S", 12), ("M", 16), ("L", 14), ("XL", 8)],
            ),
            (
                "Майка Muay Thai Pro",
                "tank-muay-thai-pro",
                "Спортивная майка-безрукавка для тренировок в зале.",
                Decimal("1490.00"),
                [("S", 9), ("M", 13), ("L", 10), ("XL", 5)],
            ),
        ],
    },
    "Хоккей": {
        "slug": "hockey",
        "products": [
            (
                "Джерси хоккейное Classic",
                "jersey-hockey-classic",
                "Игровое джерси из дышащей сетчатой ткани, свободный крой.",
                Decimal("3490.00"),
                [("S", 6), ("M", 10), ("L", 12), ("XL", 8)],
            ),
            (
                "Худи хоккейное Team",
                "hoodie-hockey-team",
                "Тёплое худи с командной символикой, плотный материал.",
                Decimal("4290.00"),
                [("S", 4), ("M", 7), ("L", 9), ("XL", 5)],
            ),
            (
                "Футболка хоккейная Fan",
                "tshirt-hockey-fan",
                "Болельщицкая футболка из мягкого хлопка.",
                Decimal("1790.00"),
                [("S", 14), ("M", 18), ("L", 16), ("XL", 9)],
            ),
            (
                "Поло хоккейное Club",
                "polo-hockey-club",
                "Поло с вышитой эмблемой клуба, для повседневной носки.",
                Decimal("2390.00"),
                [("S", 8), ("M", 11), ("L", 10), ("XL", 6)],
            ),
        ],
    },
}


async def seed():
    import os

    if os.getenv("ENVIRONMENT") == "production":
        print("ОТКАЗ: seed.py удаляет данные и запрещён на production.")
        print("Для первичного наполнения используйте seed_prod.py")
        return

    async with AsyncSessionLocal() as db:
        # --- Полная очистка тестовых данных в порядке зависимостей ---
        # Сносим всё, что ссылается на товары, затем сами товары и категории.
        # Пользователей не трогаем.
        await db.execute(text("DELETE FROM reviews"))
        await db.execute(text("DELETE FROM return_requests"))
        await db.execute(text("DELETE FROM payments"))
        await db.execute(text("DELETE FROM order_items"))
        await db.execute(text("DELETE FROM orders"))
        await db.execute(delete(ProductImage))
        await db.execute(delete(ProductVariant))
        await db.execute(delete(Product))
        await db.execute(delete(Category))
        await db.commit()
        await db.commit()

        # --- Наполняем новыми данными ---
        for cat_name, cat_data in DATA.items():
            category = Category(name=cat_name, slug=cat_data["slug"])
            db.add(category)
            await db.flush()

            for name, slug, desc, price, sizes in cat_data["products"]:
                product = Product(
                    category_id=category.id,
                    name=name,
                    slug=slug,
                    description=desc,
                    price=price,
                    is_active=True,
                )
                db.add(product)
                await db.flush()

                for size, stock in sizes:
                    db.add(
                        ProductVariant(product_id=product.id, size=size, stock=stock)
                    )

        await db.commit()
        print("База наполнена: 3 категории, 12 товаров с вариантами по размерам.")


if __name__ == "__main__":
    asyncio.run(seed())
