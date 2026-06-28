"""
Seed-скрипт демо-отзывов — ТОЛЬКО ДЛЯ РАЗРАБОТКИ.

Наполняет базу примерами отзывов, чтобы видеть, как блок выглядит
с контентом при настройке дизайна.

ЗАЩИТА: не запустится при ENVIRONMENT != local.
Демо-отзывы создаются от демо-пользователей с email вида demo+N@example.local —
их легко найти и удалить перед продакшеном (см. функцию clear_demo).

Запуск (в контейнере app):
    docker compose exec app python -m app.scripts.seed_reviews
Очистить демо-данные:
    docker compose exec app python -m app.scripts.seed_reviews --clear
"""

import asyncio
import sys

from sqlalchemy import select, delete

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.review import Review
from app.models.catalog import Product

DEMO_EMAIL_PREFIX = "demo+"
DEMO_EMAIL_DOMAIN = "@example.local"

# Реалистичные демо-отзывы (имя, оценка, текст)
DEMO_REVIEWS = [
    (
        "Максим К.",
        5,
        "Отличное качество, плотная ткань. Размер точно по сетке, доставка СДЭК за два дня.",
    ),
    (
        "Анна С.",
        5,
        "Заказывала для тренировок — всё супер. Швы аккуратные, не натирает.",
    ),
    (
        "Дмитрий В.",
        4,
        "Хорошая экипировка за свои деньги. Единственное — цвет чуть темнее, чем на фото.",
    ),
    (
        "Ольга П.",
        5,
        "Брали ребёнку в секцию. Качество на уровне, прослужит долго. Спасибо!",
    ),
    ("Сергей М.", 5, "Давно искал такую экипировку. Сидит отлично, материал дышит."),
    ("Екатерина Л.", 4, "Всё понравилось, пришло быстро. Рекомендую магазин."),
    ("Игорь Т.", 5, "Беру уже второй раз. Качество стабильно хорошее, размер не врёт."),
    ("Наталья Б.", 5, "Прекрасное качество пошива. Буду заказывать ещё."),
]


async def seed():
    if settings.ENVIRONMENT != "local":
        print("✗ Отказано: seed работает только при ENVIRONMENT=local")
        print(f"  Текущее окружение: {settings.ENVIRONMENT}")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        # Берём активные товары
        products = (
            (await db.execute(select(Product).where(Product.is_active.is_(True))))
            .scalars()
            .all()
        )
        if not products:
            print("✗ Нет активных товаров. Сначала добавьте товары в каталог.")
            return

        # Создаём демо-пользователей (по одному на автора отзыва)
        demo_users = []
        for i, (name, _, _) in enumerate(DEMO_REVIEWS):
            email = f"{DEMO_EMAIL_PREFIX}{i}{DEMO_EMAIL_DOMAIN}"
            existing = await db.scalar(select(User).where(User.email == email))
            if existing:
                demo_users.append(existing)
                continue
            user = User(
                email=email,
                hashed_password=hash_password("demo-pass-not-for-login"),
                full_name=name,
                is_active=True,
            )
            db.add(user)
            demo_users.append(user)
        await db.flush()

        # Раскидываем отзывы по товарам (каждому товару 2-4 отзыва)
        created = 0
        for p_idx, product in enumerate(products):
            # сколько отзывов этому товару (детерминированно, 2-4)
            n = 2 + (p_idx % 3)
            for j in range(n):
                idx = (p_idx + j) % len(DEMO_REVIEWS)
                name, rating, text = DEMO_REVIEWS[idx]
                user = demo_users[idx]
                # не дублируем: тот же user+product
                dup = await db.scalar(
                    select(Review).where(
                        Review.user_id == user.id, Review.product_id == product.id
                    )
                )
                if dup:
                    continue
                db.add(
                    Review(
                        user_id=user.id,
                        product_id=product.id,
                        rating=rating,
                        text=text,
                        is_approved=True,  # сразу одобрены, чтобы видеть на витрине
                    )
                )
                created += 1
        await db.commit()
        print(f"✓ Создано демо-отзывов: {created}")
        print(
            f"  Демо-пользователи: {len(demo_users)} (email {DEMO_EMAIL_PREFIX}*{DEMO_EMAIL_DOMAIN})"
        )
        print("  Очистить: python -m app.scripts.seed_reviews --clear")


async def clear_demo():
    """Удаляет все демо-отзывы и демо-пользователей."""
    async with AsyncSessionLocal() as db:
        demo_users = (
            (
                await db.execute(
                    select(User).where(
                        User.email.like(f"{DEMO_EMAIL_PREFIX}%{DEMO_EMAIL_DOMAIN}")
                    )
                )
            )
            .scalars()
            .all()
        )
        ids = [u.id for u in demo_users]
        if ids:
            await db.execute(delete(Review).where(Review.user_id.in_(ids)))
            await db.execute(delete(User).where(User.id.in_(ids)))
            await db.commit()
        print(f"✓ Удалено демо-пользователей: {len(ids)} (с их отзывами)")


if __name__ == "__main__":
    if "--clear" in sys.argv:
        asyncio.run(clear_demo())
    else:
        asyncio.run(seed())
