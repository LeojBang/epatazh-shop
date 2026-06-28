"""
Тестовое наполнение каталога для проверки пагинации и фильтров.
Очищает ТОЛЬКО каталог (категории, товары, варианты, фото, цвета).
НЕ трогает заказы, пользователей, возвраты.

Запуск:
    docker compose exec app python seed_test.py
или локально:
    python seed_test.py
"""

import asyncio
import random
from decimal import Decimal

from sqlalchemy import delete, text

from app.core.database import AsyncSessionLocal
from app.models.catalog import (
    Category,
    Product,
    ProductVariant,
    ProductImage,
    ProductColor,
    ProductColorImage,
)

GENDERS = ["мужское", "женское", "детское", "унисекс"]
BADGES = [None, None, None, "Хит", "Новинка"]  # чаще без бейджа
SIZES_CLOTHES = ["XS", "S", "M", "L", "XL", "XXL"]
SIZES_KIDS = ["28", "30", "32", "34", "36"]

MATERIALS = [
    "88% полиэстер, 12% эластан",
    "100% хлопок",
    "95% хлопок, 5% эластан",
    "полиэстер с влагоотводом",
    "70% хлопок, 30% полиэстер",
]
CARE = [
    "Стирка при 30°, не отбеливать",
    "Машинная стирка 40°, не гладить принт",
    "Ручная стирка, сушить в тени",
    "Стирка 30°, не сушить в машине",
]

# Категории и шаблоны названий товаров
CATEGORIES = {
    "ММА": {
        "slug": "mma",
        "icon": "🥊",
        "names": [
            "Рашгард MMA",
            "Шорты ММА",
            "Футболка Fighter",
            "Худи Champion",
            "Леггинсы Grappling",
            "Майка Combat",
            "Спарринг-шорты",
            "Компрессионка MMA",
        ],
    },
    "Муай-тай": {
        "slug": "muay-thai",
        "icon": "🔥",
        "names": [
            "Шорты Muay Thai",
            "Майка Boxer",
            "Бинты Pro",
            "Топ Thai Fighter",
            "Футболка Nak Muay",
            "Шорты Twins Style",
            "Рашгард Clinch",
        ],
    },
    "Хоккей": {
        "slug": "hockey",
        "icon": "🏒",
        "names": [
            "Джерси Team",
            "Поло Ice",
            "Тренировочная кофта",
            "Гамаши хоккейные",
            "Футболка Puck",
            "Худи Hockey Club",
            "Свитшот Ice Pro",
        ],
    },
    # "Аксессуары": {
    #     "slug": "accessories",
    #     "icon": "🧤",
    #     "names": [
    #         "Перчатки",
    #         "Защита голени",
    #         "Капа",
    #         "Налокотники",
    #         "Сумка спортивная",
    #         "Носки компрессионные",
    #         "Шапка зимняя",
    #         "Бафф",
    #     ],
    # },
}


async def seed():
    async with AsyncSessionLocal() as db:
        # --- ОЧИСТКА каталога (без заказов/юзеров) ---
        print("Очищаю каталог...")
        await db.execute(delete(ProductColorImage))
        await db.execute(delete(ProductColor))
        await db.execute(delete(ProductImage))

        # Подзапрос «товары в заказах» — их удалять нельзя.
        # NULL-safe: добавляем фиктивный UUID чтобы NOT IN не сломался на пустом списке.
        protected_sub = """
            SELECT DISTINCT p.id FROM products p
            JOIN product_variants v ON v.product_id = p.id
            JOIN order_items oi ON oi.variant_id = v.id
            UNION SELECT '00000000-0000-0000-0000-000000000000'::uuid
        """

        # Отзывы и избранное у товаров которые будем удалять
        await db.execute(
            text(f"DELETE FROM reviews WHERE product_id NOT IN ({protected_sub})")
        )
        await db.execute(
            text(f"DELETE FROM favorites WHERE product_id NOT IN ({protected_sub})")
        )

        # Варианты не из заказов
        await db.execute(
            text("""
            DELETE FROM product_variants
            WHERE id NOT IN (
                SELECT variant_id FROM order_items WHERE variant_id IS NOT NULL
                UNION SELECT '00000000-0000-0000-0000-000000000000'::uuid
            )
        """)
        )
        # Товары не из заказов
        await db.execute(
            text(f"DELETE FROM products WHERE id NOT IN ({protected_sub})")
        )
        # Пустые категории
        await db.execute(
            text("""
            DELETE FROM categories
            WHERE id NOT IN (
                SELECT DISTINCT category_id FROM products
                UNION SELECT '00000000-0000-0000-0000-000000000000'::uuid
            )
        """)
        )
        await db.commit()

        # --- СОЗДАНИЕ ---
        print("Создаю категории и товары...")
        slug_counter = 0
        total_products = 0

        for cat_name, cat_data in CATEGORIES.items():
            # Категория (создаём заново или находим)
            result = await db.execute(
                text("SELECT id FROM categories WHERE slug = :slug"),
                {"slug": cat_data["slug"]},
            )
            existing = result.first()
            if existing:
                cat_id = existing[0]
            else:
                cat = Category(
                    name=cat_name, slug=cat_data["slug"], icon=cat_data["icon"]
                )
                db.add(cat)
                await db.flush()
                cat_id = cat.id

            # Товары — создаём по 5-7 вариаций каждого названия с разными полами
            for base_name in cat_data["names"]:
                # Для каждого названия — 2-3 варианта с разным полом
                for _ in range(random.randint(2, 3)):
                    slug_counter += 1
                    gender = random.choice(GENDERS)
                    is_kids = gender == "детское"
                    price = Decimal(
                        str(
                            random.choice(
                                [1290, 1590, 1890, 2290, 2490, 2890, 3290, 3990, 4500]
                            )
                        )
                    )
                    has_sale = random.random() < 0.25
                    sale_price = (
                        (price - Decimal(str(random.choice([200, 300, 500]))))
                        if has_sale
                        else None
                    )

                    gender_label = {
                        "мужское": "муж",
                        "женское": "жен",
                        "детское": "дет",
                        "унисекс": "уни",
                    }[gender]
                    name = f"{base_name} ({gender_label})"

                    product = Product(
                        category_id=cat_id,
                        name=name,
                        slug=f"{cat_data['slug']}-{slug_counter}",
                        description=f"{base_name} — качественная экипировка для тренировок и соревнований.",
                        material=random.choice(MATERIALS),
                        care=random.choice(CARE),
                        gender=gender,
                        price=price,
                        sale_price=sale_price,
                        badge=random.choice(BADGES),
                        is_active=True,
                    )
                    db.add(product)
                    await db.flush()

                    # Размеры
                    sizes = SIZES_KIDS if is_kids else SIZES_CLOTHES
                    chosen = random.sample(sizes, random.randint(3, len(sizes)))
                    for sz in chosen:
                        db.add(
                            ProductVariant(
                                product_id=product.id,
                                size=sz,
                                stock=random.choice([0, 0, 3, 5, 8, 12, 20]),
                            )
                        )
                    total_products += 1

            await db.commit()
            print(f"  {cat_data['icon']} {cat_name}: товары добавлены")

        print(f"\nГотово! Создано товаров: {total_products}")
        print("Фото нет (добавишь через админку). Проверяй пагинацию и фильтры.")


if __name__ == "__main__":
    asyncio.run(seed())
