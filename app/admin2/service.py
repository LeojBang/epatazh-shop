"""Сервис для кастомной админки — все запросы к БД."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cdek import service as cdek_service
from app.core.logging_config import get_logger
from app.models.payment import Payment
from app.payments import service as payment_service
from app.models.catalog import (
    Category,
    Product,
    ProductColor,
    ProductColorImage,
    ProductImage,
    ProductVariant,
)
from app.models.order import Order, OrderItem
from app.models.return_request import ReturnRequest
from app.models.user import User

logger = get_logger("admin")


# ─── ТОВАРЫ ──────────────────────────────────────────────────────────────────


async def get_products_list(
    db: AsyncSession,
    search: str = "",
    category_slug: str | None = None,
    status: str = "all",
    page: int = 1,
    per_page: int = 30,
) -> tuple[list[Product], int]:
    q = (
        select(Product)
        .options(selectinload(Product.category), selectinload(Product.variants))
        .order_by(Product.name)
    )
    if search:
        q = q.where(Product.name.ilike(f"%{search}%"))
    if category_slug:
        q = q.join(Category).where(Category.slug == category_slug)
    if status == "active":
        q = q.where(Product.is_active)
    elif status == "hidden":
        q = q.where(~Product.is_active)

    total = await db.scalar(
        select(func.count()).select_from(q.order_by(None).subquery())
    )
    q = q.limit(per_page).offset((page - 1) * per_page)
    result = await db.execute(q)
    return list(result.scalars().all()), total or 0


async def get_product_for_edit(
    db: AsyncSession, product_id: uuid.UUID
) -> Product | None:
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.category),
            selectinload(Product.variants),
            selectinload(Product.images),
            selectinload(Product.colors).selectinload(ProductColor.images),
        )
    )
    return result.scalar_one_or_none()


async def slug_is_taken(db: AsyncSession, slug: str, exclude_id=None) -> bool:
    """Проверяет, занят ли slug другим товаром."""
    q = select(Product.id).where(Product.slug == slug)
    if exclude_id:
        q = q.where(Product.id != exclude_id)
    return await db.scalar(q) is not None


async def create_product(db: AsyncSession, data: dict) -> Product:
    product = Product(**data)
    db.add(product)
    await db.flush()
    return product


async def update_product(db: AsyncSession, product: Product, data: dict) -> Product:
    for key, value in data.items():
        setattr(product, key, value)
    await db.flush()
    return product


async def delete_product(db: AsyncSession, product: Product) -> bool:
    """Удаляет товар.

    Если хотя бы один вариант товара уже присутствует в заказах,
    товар физически не удаляется, а скрывается (is_active=False).

    Возвращает:
        True — если товар удалён.
        False — если товар скрыт.
    """
    from app.models.catalog import ProductVariant
    from app.models.order import OrderItem
    from app.models.review import Review
    from sqlalchemy import delete as sa_delete, exists, select

    # Получаем ID всех вариантов товара
    variant_ids = (
        await db.scalars(
            select(ProductVariant.id).where(ProductVariant.product_id == product.id)
        )
    ).all()

    if variant_ids:
        # Проверяем наличие в заказах
        in_orders = await db.scalar(
            select(exists().where(OrderItem.variant_id.in_(variant_ids)))
        )

        if in_orders:
            product.is_active = False
            await db.flush()
            return False

    # Удаляем отзывы
    await db.execute(sa_delete(Review).where(Review.product_id == product.id))

    # Удаляем товар
    await db.delete(product)
    await db.flush()

    return True


# ─── ВАРИАНТЫ (размеры) ──────────────────────────────────────────────────────


async def upsert_variants(
    db: AsyncSession,
    product_id: uuid.UUID,
    sizes_stock: dict[str, int],
) -> None:
    """Обновляет/создаёт варианты товара по размерам.
    sizes_stock = {"XS": 5, "S": 10, "M": 0}
    Размеры которые есть в заказах не удаляем (ставим stock=0) — чтобы не ломать историю.
    """
    from app.models.order import OrderItem

    result = await db.execute(
        select(ProductVariant).where(ProductVariant.product_id == product_id)
    )
    existing = {v.size: v for v in result.scalars().all()}

    for size, stock in sizes_stock.items():
        if not size.strip():
            continue
        stock = max(0, int(stock))
        if size in existing:
            existing[size].stock = stock
        else:
            db.add(ProductVariant(product_id=product_id, size=size, stock=stock))

    # Размеры которых больше нет в форме — удаляем, но только если не в заказах
    for size, variant in existing.items():
        if size not in sizes_stock:
            # Проверяем, есть ли вариант в заказах
            in_orders = await db.scalar(
                select(func.count())
                .select_from(OrderItem)
                .where(OrderItem.variant_id == variant.id)
            )
            if in_orders:
                # Нельзя удалить — оставляем, но обнуляем остаток
                variant.stock = 0
            else:
                await db.delete(variant)

    await db.flush()


# ─── ФОТО ТОВАРА ─────────────────────────────────────────────────────────────


async def add_product_image(
    db: AsyncSession, product_id: uuid.UUID, path: str, position: int = 0
) -> ProductImage:
    img = ProductImage(product_id=product_id, path=path, position=position)
    db.add(img)
    await db.flush()
    return img


async def delete_product_image(db: AsyncSession, image_id: uuid.UUID) -> None:
    result = await db.execute(select(ProductImage).where(ProductImage.id == image_id))
    img = result.scalar_one_or_none()
    if img:
        await db.delete(img)
        await db.flush()


# ─── ЦВЕТА ───────────────────────────────────────────────────────────────────


async def upsert_color(
    db: AsyncSession,
    product_id: uuid.UUID,
    color_id: uuid.UUID | None,
    name: str,
    hex_code: str,
    position: int = 0,
) -> ProductColor:
    if color_id:
        result = await db.execute(
            select(ProductColor).where(ProductColor.id == color_id)
        )
        color = result.scalar_one_or_none()
        if color:
            color.name = name
            color.hex = hex_code
            color.position = position
            await db.flush()
            return color

    color = ProductColor(
        product_id=product_id, name=name, hex=hex_code, position=position
    )
    db.add(color)
    await db.flush()
    return color


async def delete_color(db: AsyncSession, color_id: uuid.UUID) -> None:
    result = await db.execute(select(ProductColor).where(ProductColor.id == color_id))
    color = result.scalar_one_or_none()
    if color:
        await db.delete(color)
        await db.flush()


async def add_color_image(
    db: AsyncSession, color_id: uuid.UUID, path: str, position: int = 0
) -> ProductColorImage:
    img = ProductColorImage(color_id=color_id, path=path, position=position)
    db.add(img)
    await db.flush()
    return img


async def delete_color_image(db: AsyncSession, image_id: uuid.UUID) -> None:
    result = await db.execute(
        select(ProductColorImage).where(ProductColorImage.id == image_id)
    )
    img = result.scalar_one_or_none()
    if img:
        await db.delete(img)
        await db.flush()


# ─── КАТЕГОРИИ ───────────────────────────────────────────────────────────────


async def get_categories_list(db: AsyncSession) -> list[Category]:
    result = await db.execute(
        select(Category)
        .options(selectinload(Category.products))
        .order_by(Category.name)
    )
    return list(result.scalars().all())


async def get_category(db: AsyncSession, category_id: uuid.UUID) -> Category | None:
    result = await db.execute(select(Category).where(Category.id == category_id))
    return result.scalar_one_or_none()


async def create_category(db: AsyncSession, data: dict) -> Category:
    cat = Category(**data)
    db.add(cat)
    await db.flush()
    return cat


async def update_category(db: AsyncSession, cat: Category, data: dict) -> Category:
    for key, value in data.items():
        setattr(cat, key, value)
    await db.flush()
    return cat


async def delete_category(db: AsyncSession, cat: Category) -> bool:
    """Удаляет категорию. Если в ней есть товары — не удаляет (возвращает False)."""
    from app.models.catalog import Product

    products_count = await db.scalar(
        select(func.count()).select_from(Product).where(Product.category_id == cat.id)
    )
    if products_count:
        return False

    await db.delete(cat)
    await db.flush()
    return True


# ─── ЗАКАЗЫ ──────────────────────────────────────────────────────────────────


async def get_orders_list(
    db: AsyncSession,
    status_filter: str = "all",
    page: int = 1,
    per_page: int = 30,
) -> tuple[list[Order], int]:
    q = select(Order).order_by(Order.created_at.desc())
    if status_filter != "all":
        q = q.where(Order.status == status_filter)

    total = await db.scalar(
        select(func.count()).select_from(q.order_by(None).subquery())
    )
    q = q.limit(per_page).offset((page - 1) * per_page)
    result = await db.execute(q)
    return list(result.scalars().all()), total or 0


async def get_order_detail(db: AsyncSession, order_id: uuid.UUID) -> Order | None:
    result = await db.execute(
        select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    )
    return result.scalar_one_or_none()


class StatusTransitionError(Exception):
    """Недопустимая смена статуса заказа (например из финального состояния)."""


# Машина состояний заказа: из какого статуса в какие можно перейти.
# «delivered» и «cancelled» — финальные (пустое множество), выйти из них нельзя.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "new": {"pending", "paid", "cancelled"},
    "pending": {"paid", "cancelled"},
    "paid": {"shipped", "delivered", "cancelled"},
    "shipped": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
}


async def update_order_status(db: AsyncSession, order: Order, new_status: str) -> str:
    """Меняет статус заказа и запускает реальные действия при отмене.

    Смена статуса разрешена только по машине состояний ALLOWED_TRANSITIONS —
    из финальных статусов («delivered», «cancelled») выйти нельзя. Это защищает
    от повторной отмены (двойной возврат склада/денег) и нелогичных переходов.

    При переводе в «cancelled» (из не-отменённого статуса):
      1. отменяет заказ в СДЭК, если он был зарегистрирован;
      2. возвращает деньги в YooKassa, если заказ был оплачен;
      3. возвращает товары на склад.

    Возвращает ПРЕДЫДУЩИЙ статус — чтобы вызывающий код решил,
    отправлять ли письмо покупателю. При недопустимом переходе бросает
    StatusTransitionError (побочные действия не выполняются).
    """
    old_status = order.status
    if new_status == old_status:
        return old_status

    if new_status not in ALLOWED_TRANSITIONS.get(old_status, set()):
        raise StatusTransitionError(
            f"Нельзя сменить статус «{old_status}» → «{new_status}»"
        )

    if new_status == "cancelled":
        # 1. Отмена заказа в СДЭК (best-effort, не роняет отмену)
        if order.cdek_order_uuid:
            await cdek_service.cancel_order_in_cdek(order)

        # 2. Возврат денег, если заказ был оплачен
        if old_status in ("paid", "shipped", "delivered"):
            payment = await db.scalar(
                select(Payment).where(
                    Payment.order_id == order.id,
                    Payment.status == "succeeded",
                )
            )
            if payment and payment.external_id:
                try:
                    await payment_service.create_refund(
                        payment.external_id, order.total
                    )
                    logger.info("Возврат по заказу %s инициирован", order.id)
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "Не удалось вернуть деньги по заказу %s: %s", order.id, e
                    )

        # 3. Возврат товаров на склад
        for item in order.items:
            if item.variant_id:
                await db.execute(
                    text(
                        "UPDATE product_variants SET stock = stock + :qty WHERE id = :id"
                    ),
                    {"qty": item.quantity, "id": item.variant_id},
                )

    order.status = new_status
    await db.flush()
    return old_status


# ─── ВОЗВРАТЫ ────────────────────────────────────────────────────────────────


async def get_returns_list(
    db: AsyncSession,
    status_filter: str = "all",
    page: int = 1,
    per_page: int = 30,
) -> tuple[list[ReturnRequest], int]:
    q = select(ReturnRequest).order_by(ReturnRequest.created_at.desc())
    if status_filter != "all":
        q = q.where(ReturnRequest.status == status_filter)

    total = await db.scalar(
        select(func.count()).select_from(q.order_by(None).subquery())
    )
    q = q.limit(per_page).offset((page - 1) * per_page)
    result = await db.execute(q)
    return list(result.scalars().all()), total or 0


async def get_return_detail(
    db: AsyncSession, return_id: uuid.UUID
) -> ReturnRequest | None:
    result = await db.execute(
        select(ReturnRequest).where(ReturnRequest.id == return_id)
    )
    return result.scalar_one_or_none()


async def update_return(
    db: AsyncSession,
    ret: ReturnRequest,
    new_status: str,
    admin_comment: str | None = None,
) -> ReturnRequest:
    ret.status = new_status
    if admin_comment is not None:
        ret.admin_comment = admin_comment
    await db.flush()
    return ret


# ─── ПОЛЬЗОВАТЕЛИ ────────────────────────────────────────────────────────────


async def get_users_list(
    db: AsyncSession,
    search: str = "",
    page: int = 1,
    per_page: int = 30,
) -> tuple[list[User], int]:
    q = select(User).order_by(User.created_at.desc())
    if search:
        q = q.where(User.email.ilike(f"%{search}%"))

    total = await db.scalar(
        select(func.count()).select_from(q.order_by(None).subquery())
    )
    q = q.limit(per_page).offset((page - 1) * per_page)
    result = await db.execute(q)
    return list(result.scalars().all()), total or 0


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def update_user(db: AsyncSession, user: User, data: dict) -> User:
    for key, value in data.items():
        setattr(user, key, value)
    await db.flush()
    return user


async def count_superusers(db: AsyncSession) -> int:
    return (
        await db.scalar(select(func.count()).select_from(User).where(User.is_superuser))
        or 0
    )


# ─── АНАЛИТИКА ───────────────────────────────────────────────────────────────


async def get_analytics_summary(db: AsyncSession, days: int = 30) -> dict:
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(days=days)

    revenue = await db.scalar(
        select(func.sum(Order.total)).where(
            Order.created_at >= since,
            Order.status.in_(["paid", "shipped", "delivered"]),
        )
    ) or Decimal("0")

    orders_count = (
        await db.scalar(select(func.count()).where(Order.created_at >= since)) or 0
    )

    new_users = (
        await db.scalar(select(func.count()).where(User.created_at >= since)) or 0
    )

    avg_order = revenue / orders_count if orders_count else Decimal("0")

    # Новые заказы (статус new)
    new_orders = await db.scalar(select(func.count()).where(Order.status == "new")) or 0

    # Топ товаров
    top_result = await db.execute(
        select(
            OrderItem.product_name,
            func.sum(OrderItem.quantity),
            func.sum(OrderItem.price * OrderItem.quantity),
        )
        .join(Order)
        .where(
            Order.created_at >= since,
            Order.status.in_(["paid", "shipped", "delivered"]),
        )
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.price * OrderItem.quantity).desc())
        .limit(5)
    )
    top_products = [
        {"name": row[0], "qty": row[1], "revenue": row[2]} for row in top_result.all()
    ]

    return {
        "revenue": revenue,
        "orders_count": orders_count,
        "new_users": new_users,
        "avg_order": avg_order,
        "new_orders": new_orders,
        "top_products": top_products,
        "days": days,
    }
