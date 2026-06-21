from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderItem


async def get_summary(db: AsyncSession, days: int = 30) -> dict:
    """Сводные метрики за последние `days` дней."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Выручка и число оплаченных заказов
    paid_result = await db.execute(
        select(func.coalesce(func.sum(Order.total), 0), func.count(Order.id)).where(
            Order.status == "paid", Order.created_at >= since
        )
    )
    revenue, paid_count = paid_result.one()

    # Всего созданных заказов (для конверсии оплаты)
    total_result = await db.execute(
        select(func.count(Order.id)).where(Order.created_at >= since)
    )
    total_count = total_result.scalar_one()

    avg_check = (Decimal(revenue) / paid_count) if paid_count else Decimal("0")
    pay_conversion = (paid_count / total_count * 100) if total_count else 0

    return {
        "revenue": Decimal(revenue),
        "paid_count": paid_count,
        "total_count": total_count,
        "avg_check": round(avg_check, 2),
        "pay_conversion": round(pay_conversion, 1),
        "days": days,
    }


async def get_top_products(
    db: AsyncSession, days: int = 30, limit: int = 10
) -> list[dict]:
    """Топ товаров по количеству проданных штук (по оплаченным заказам)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("qty"),
            func.sum(OrderItem.price * OrderItem.quantity).label("revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status == "paid", Order.created_at >= since)
        .group_by(OrderItem.product_name)
        .order_by(desc("qty"))
        .limit(limit)
    )
    return [
        {"name": row.product_name, "qty": row.qty, "revenue": row.revenue}
        for row in result.all()
    ]


async def get_revenue_by_day(db: AsyncSession, days: int = 30) -> list[dict]:
    """Выручка по дням для графика."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            func.date(Order.created_at).label("day"),
            func.sum(Order.total).label("revenue"),
        )
        .where(Order.status == "paid", Order.created_at >= since)
        .group_by(func.date(Order.created_at))
        .order_by("day")
    )
    return [
        {"day": row.day.strftime("%d.%m"), "revenue": float(row.revenue)}
        for row in result.all()
    ]
