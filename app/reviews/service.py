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
        .where(Review.product_id == product_id, Review.is_approved == True)
        .options(selectinload(Review.user))
        .order_by(Review.created_at.desc())
    )
    return list(result.scalars().all())


async def get_rating_summary(db: AsyncSession, product_id: str) -> tuple[float, int]:
    """Средняя оценка и количество одобренных отзывов."""
    result = await db.execute(
        select(func.avg(Review.rating), func.count(Review.id)).where(
            Review.product_id == product_id, Review.is_approved == True
        )
    )
    avg, count = result.one()
    return (round(float(avg), 1) if avg else 0.0, count or 0)