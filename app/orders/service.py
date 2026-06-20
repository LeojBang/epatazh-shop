from datetime import datetime, timezone, timedelta
from decimal import Decimal

import redis.asyncio as redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cart import service as cart_service
from app.models.catalog import Product
from app.models.order import Order, OrderItem


class CheckoutError(Exception):
    """Ошибка оформления, которую показываем пользователю."""


async def create_order(
    db: AsyncSession,
    r: redis.Redis,
    cart_user_id: str,
    *,
    user_id: str | None,
    email: str,
    phone: str,
    full_name: str,
    address: str,
) -> Order:
    cart = await cart_service.get_cart(r, cart_user_id)
    if not cart:
        raise CheckoutError("Корзина пуста")

    # Загружаем товары одним запросом по списку slug из корзины
    result = await db.execute(
        select(Product).where(Product.slug.in_(list(cart.keys())))
    )
    products = {p.slug: p for p in result.scalars().all()}

    order_items: list[OrderItem] = []
    total = Decimal("0.00")

    for slug, qty in cart.items():
        product = products.get(slug)
        if not product:
            raise CheckoutError(f"Товар {slug} больше не доступен")

        # АТОМАРНОЕ СПИСАНИЕ: условие stock >= qty прямо в UPDATE.
        # rowcount == 0 означает, что товара не хватило — списание не произошло.
        update_result = await db.execute(
            text(
                "UPDATE products SET stock = stock - :qty "
                "WHERE id = :id AND stock >= :qty"
            ),
            {"qty": qty, "id": product.id},
        )
        if update_result.rowcount == 0:
            raise CheckoutError(
                f"Недостаточно товара «{product.name}» на складе"
            )

        subtotal = product.price * qty
        total += subtotal
        order_items.append(
            OrderItem(
                product_id=product.id,
                product_name=product.name,
                price=product.price,
                quantity=qty,
            )
        )

    order = Order(
        user_id=user_id,
        status="pending",
        total=total,
        email=email,
        phone=phone,
        full_name=full_name,
        address=address,
        items=order_items,
    )
    db.add(order)

    await db.commit()
    await db.refresh(order)

    # Корзину очищаем только после успешного коммита
    await cart_service.clear_cart(r, cart_user_id)

    return order


async def get_order(db: AsyncSession, order_id: str) -> Order | None:
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items))
    )
    return result.scalar_one_or_none()


async def get_user_orders(db: AsyncSession, user_id: str) -> list[Order]:
    result = await db.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
    )
    return list(result.scalars().all())


async def cancel_order_stock(db: AsyncSession, order: Order) -> None:
    """Отменяет заказ и возвращает товар его позиций на склад. Атомарно в транзакции."""
    from sqlalchemy import text

    for item in order.items:
        # Возвращаем количество обратно на склад
        await db.execute(
            text("UPDATE products SET stock = stock + :qty WHERE id = :id"),
            {"qty": item.quantity, "id": item.product_id},
        )

    order.status = "cancelled"
    await db.commit()


async def cancel_expired_orders(db: AsyncSession, max_age_minutes: int = 15) -> int:
    """Находит pending-заказы старше max_age_minutes и отменяет их. Возвращает число отменённых."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

    result = await db.execute(
        select(Order)
        .where(Order.status == "pending", Order.created_at < cutoff)
        .options(selectinload(Order.items))
    )
    expired = list(result.scalars().all())

    for order in expired:
        await cancel_order_stock(db, order)

    return len(expired)
