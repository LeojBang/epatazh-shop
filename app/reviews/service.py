from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order, OrderItem
from app.models.review import Review


class ReviewError(Exception):
    """Ошибка добавления отзыва, показываемая пользователю."""


async def has_purchased(db: AsyncSession, user_id: str, product_id: str) -> bool:
    """Проверяет, есть ли у пользователя оплаченный заказ с этим товаром."""
    result = await db.execute(
        select(OrderItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.user_id == user_id,
            Order.status == "paid",
            OrderItem.product_id == product_id,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def get_existing_review(
    db: AsyncSession, user_id: str, product_id: str
) -> Review | None:
    result = await db.execute(
        select(Review).where(Review.user_id == user_id, Review.product_id == product_id)
    )
    return result.scalar_one_or_none()


async def create_review(
    db: AsyncSession,
    user_id: str,
    product_id: str,
    rating: int,
    text: str,
) -> Review:
    if rating < 1 or rating > 5:
        raise ReviewError("Оценка должна быть от 1 до 5")

    if not text.strip():
        raise ReviewError("Текст отзыва не может быть пустым")

    if not await has_purchased(db, user_id, product_id):
        raise ReviewError("Отзыв можно оставить только на купленный товар")

    if await get_existing_review(db, user_id, product_id):
        raise ReviewError("Вы уже оставляли отзыв на этот товар")

    review = Review(
        user_id=user_id,
        product_id=product_id,
        rating=rating,
        text=text.strip(),
        is_approved=False,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def get_approved_reviews(db: AsyncSession, product_id: str) -> list[Review]:
    """Одобренные отзывы товара, для показа на странице."""
    result = await db.execute(
        select(Review)
        .where(Review.product_id == product_id, Review.is_approved)
        .options(selectinload(Review.user))
        .order_by(Review.created_at.desc())
    )
    return list(result.scalars().all())


async def get_rating_summary(db: AsyncSession, product_id: str) -> tuple[float, int]:
    """Средняя оценка и количество одобренных отзывов."""
    result = await db.execute(
        select(func.avg(Review.rating), func.count(Review.id)).where(
            Review.product_id == product_id, Review.is_approved
        )
    )
    avg, count = result.one()
    return (round(float(avg), 1) if avg else 0.0, count or 0)


# ─── Админка: модерация отзывов ──────────────────────────────────────────────


async def get_all_reviews(db: AsyncSession, only_pending: bool = False) -> list[Review]:
    """Все отзывы для модерации (с товаром и автором). Новые сверху."""
    q = (
        select(Review)
        .options(selectinload(Review.user), selectinload(Review.product))
        .order_by(Review.created_at.desc())
    )
    if only_pending:
        q = q.where(Review.is_approved.is_(False))
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_pending_count(db: AsyncSession) -> int:
    """Сколько отзывов ждут модерации (для счётчика в меню)."""
    return (
        await db.scalar(
            select(func.count())
            .select_from(Review)
            .where(Review.is_approved.is_(False))
        )
        or 0
    )


async def approve_review(db: AsyncSession, review_id: str) -> bool:
    """Одобряет отзыв — он становится виден на витрине."""
    review = await db.get(Review, review_id)
    if not review:
        return False
    review.is_approved = True
    await db.commit()
    return True


async def delete_review(db: AsyncSession, review_id: str) -> bool:
    """Удаляет отзыв (отклонение модерации)."""
    review = await db.get(Review, review_id)
    if not review:
        return False
    await db.delete(review)
    await db.commit()
    return True
