import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.return_request import ReturnRequest
from app.models.order import Order


class ReturnError(Exception):
    """Ошибка оформления возврата (показывается покупателю)."""


# Причины возврата — фиксированный список (код → русская подпись)
RETURN_REASONS = {
    "size": "Не подошёл размер",
    "look": "Не понравился / не подошёл",
    "defect": "Брак / дефект",
    "other": "Другая причина",
}

# Срок на возврат товара надлежащего качества — 14 дней
RETURN_WINDOW_DAYS = 14

# Статусы, при которых заказ можно вернуть (оплачен и далее)
RETURNABLE_STATUSES = {"paid", "shipped", "delivered"}


async def create_return_request(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
    comment: str | None,
) -> ReturnRequest:
    """Создаёт заявку на возврат с проверками."""
    # 1. Причина должна быть из списка
    if reason not in RETURN_REASONS:
        raise ReturnError("Некорректная причина возврата")

    # 2. Заказ существует и принадлежит этому пользователю
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    if not order:
        raise ReturnError("Заказ не найден")

    # 3. Заказ должен быть оплачен (нельзя вернуть неоплаченный)
    if order.status not in RETURNABLE_STATUSES:
        raise ReturnError("Возврат возможен только для оплаченных заказов")

    # 4. Проверка срока 14 дней с момента заказа
    #    (брак — без ограничения срока, для него пропускаем проверку)
    if reason != "defect":
        deadline = order.created_at + timedelta(days=RETURN_WINDOW_DAYS)
        if datetime.now(timezone.utc) > deadline:
            raise ReturnError(
                f"Срок возврата ({RETURN_WINDOW_DAYS} дней) истёк. "
                "Для возврата бракованного товара выберите причину «Брак»."
            )

    # 5. Нельзя подать повторную заявку, если уже есть активная
    existing = await db.scalar(
        select(ReturnRequest).where(
            ReturnRequest.order_id == order_id,
            ReturnRequest.status.in_(["pending", "approved"]),
        )
    )
    if existing:
        raise ReturnError("По этому заказу уже есть активная заявка на возврат")

    # Создаём заявку
    return_request = ReturnRequest(
        order_id=order_id,
        user_id=user_id,
        reason=reason,
        comment=comment,
        status="pending",
    )
    db.add(return_request)
    await db.commit()
    await db.refresh(return_request)
    return return_request


async def get_user_returns(db: AsyncSession, user_id: uuid.UUID) -> list[ReturnRequest]:
    """Все заявки на возврат пользователя (новые сверху)."""
    result = await db.execute(
        select(ReturnRequest)
        .where(ReturnRequest.user_id == user_id)
        .order_by(ReturnRequest.created_at.desc())
    )
    return list(result.scalars().all())
