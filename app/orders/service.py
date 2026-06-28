from datetime import datetime, timezone, timedelta
from decimal import Decimal

import redis.asyncio as redis
from sqlalchemy import String, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cart import service as cart_service
from app.models import Product
from app.models.order import Order, OrderItem
from app.core.logging_config import get_logger

logger = get_logger("orders")


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
    delivery_type: str = "pvz",
    cdek_city_code: int | None = None,
    cdek_city_name: str | None = None,
    cdek_pvz_code: str | None = None,
    cdek_pvz_address: str | None = None,
) -> Order:
    cart = await cart_service.get_cart(r, cart_user_id)
    if not cart:
        raise CheckoutError("Корзина пуста")

    from app.models.catalog import ProductVariant

    # Загружаем варианты по id из корзины, вместе с товаром (для цены и названия)
    result = await db.execute(
        select(ProductVariant)
        .where(ProductVariant.id.in_(list(cart.keys())))
        .options(selectinload(ProductVariant.product).selectinload(Product.images))
    )
    variants = {str(v.id): v for v in result.scalars().all()}

    order_items: list[OrderItem] = []
    total = Decimal("0.00")

    for variant_id, qty in cart.items():
        variant = variants.get(variant_id)
        if not variant or not variant.product:
            raise CheckoutError("Один из товаров больше не доступен")

        # Атомарное списание остатка ВАРИАНТА
        update_result = await db.execute(
            text(
                "UPDATE product_variants SET stock = stock - :qty "
                "WHERE id = :id AND stock >= :qty"
            ),
            {"qty": qty, "id": variant.id},
        )
        if update_result.rowcount == 0:
            raise CheckoutError(
                f"Недостаточно товара «{variant.product.name}» (размер {variant.size})"
            )

        subtotal = variant.product.effective_price * qty
        total += subtotal
        image_path = variant.product.images[0].path if variant.product.images else None
        order_items.append(
            OrderItem(
                product_id=variant.product.id,
                variant_id=variant.id,
                product_name=variant.product.name,
                product_image=image_path,
                size=variant.size,
                price=variant.product.effective_price,
                quantity=qty,
                weight=variant.product.weight or 500,
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
        delivery_type=delivery_type,
        cdek_city_code=cdek_city_code,
        cdek_city_name=cdek_city_name,
        cdek_pvz_code=cdek_pvz_code,
        cdek_pvz_address=cdek_pvz_address,
        items=order_items,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    await cart_service.clear_cart(r, cart_user_id)

    logger.info(
        "Создан заказ %s на сумму %s (%s позиций)", order.id, total, len(order_items)
    )

    return order


async def get_order(db: AsyncSession, order_id: str) -> Order | None:
    result = await db.execute(
        select(Order).where(Order.id == order_id).options(selectinload(Order.items))
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


async def cancel_order_return_stock(db: AsyncSession, order: Order) -> None:
    """Отменяет заказ и возвращает товар его позиций на склад варианта."""
    from sqlalchemy import text

    for item in order.items:
        if item.variant_id:
            await db.execute(
                text("UPDATE product_variants SET stock = stock + :qty WHERE id = :id"),
                {"qty": item.quantity, "id": item.variant_id},
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
    if expired:
        logger.info("Автоотмена: отменено заказов %s", len(expired))

    for order in expired:
        await cancel_order_return_stock(db, order)

    return len(expired)


async def find_order_by_short_id(db: AsyncSession, short_id: str) -> Order | None:
    """
    Ищет заказ по началу UUID (короткий номер, который видит покупатель).
    Используется на странице отслеживания, если ввели короткий номер.
    """
    short = short_id.strip().lower()
    if len(short) < 6:  # слишком коротко — не ищем, чтобы не было коллизий
        return None
    result = await db.execute(
        select(Order)
        .where(func.cast(Order.id, String).ilike(f"{short}%"))
        .options(selectinload(Order.items))
        .limit(2)
    )
    rows = list(result.scalars().all())
    # если под префикс попало больше одного — неоднозначно, не возвращаем
    return rows[0] if len(rows) == 1 else None
