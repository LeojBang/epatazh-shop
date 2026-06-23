from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.favorite import Favorite
from app.models.catalog import Product


async def is_favorite(db: AsyncSession, user_id, product_id) -> bool:
    """Проверяет, в избранном ли товар у пользователя."""
    result = await db.scalar(
        select(Favorite.id).where(
            Favorite.user_id == user_id, Favorite.product_id == product_id
        )
    )
    return result is not None


async def toggle_favorite(db: AsyncSession, user_id, product_id) -> bool:
    """Добавляет товар в избранное или убирает, если уже был.

    Возвращает True, если товар теперь в избранном, False — если убран.
    """
    existing = await db.scalar(
        select(Favorite).where(
            Favorite.user_id == user_id, Favorite.product_id == product_id
        )
    )
    if existing:
        await db.delete(existing)
        await db.commit()
        return False
    else:
        favorite = Favorite(user_id=user_id, product_id=product_id)
        db.add(favorite)
        await db.commit()
        return True


async def get_user_favorites(db: AsyncSession, user_id) -> list[Product]:
    """Список товаров в избранном пользователя (с данными для карточек)."""
    result = await db.execute(
        select(Product)
        .join(Favorite, Favorite.product_id == Product.id)
        .where(Favorite.user_id == user_id, Product.is_active)
        .options(
            selectinload(Product.category),
            selectinload(Product.variants),
            selectinload(Product.images),
        )
        .order_by(Favorite.created_at.desc())
    )
    return list(result.scalars().all())


async def get_favorite_count(db: AsyncSession, user_id) -> int:
    """Сколько товаров в избранном (для счётчика в шапке)."""
    return (
        await db.scalar(
            select(func.count())
            .select_from(Favorite)
            .where(Favorite.user_id == user_id)
        )
        or 0
    )


async def get_favorite_ids(db: AsyncSession, user_id) -> set:
    """Множество id товаров в избранном — чтобы на карточках показать состояние сердечка."""
    result = await db.execute(
        select(Favorite.product_id).where(Favorite.user_id == user_id)
    )
    return {row[0] for row in result.all()}
