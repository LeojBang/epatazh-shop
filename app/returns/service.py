import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.return_request import ReturnRequest
from app.models.order import Order
from app.models.payment import Payment
from app.payments import service as payment_service


class ReturnError(Exception):
    """Ошибка оформления возврата (показывается покупателю)."""


# Причины возврата — фиксированный список (код → русская подпись)
RETURN_REASONS = {
    "size": "Не подошёл размер",
    "defect": "Брак или дефект",
    "mismatch": "Не соответствует описанию или фото",
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

    # 5. Проверка существующих заявок по заказу.
    #    pending/approved — заявка в работе, нельзя дублировать.
    #    refunded — деньги уже вернули, возвращать нечего.
    #    rejected — была отклонена, разрешаем повторную попытку.
    existing = await db.scalar(
        select(ReturnRequest).where(
            ReturnRequest.order_id == order_id,
            ReturnRequest.status.in_(["pending", "approved", "refunded"]),
        )
    )
    if existing:
        if existing.status == "refunded":
            raise ReturnError("По этому заказу деньги уже возвращены")
        raise ReturnError("По этому заказу уже есть заявка на возврат в обработке")

    # Находим id платежа в YooKassa — чтобы менеджер быстро нашёл его в кабинете
    payment = await db.scalar(
        select(Payment)
        .where(Payment.order_id == order_id, Payment.status == "succeeded")
        .order_by(Payment.created_at.desc())
    )
    payment_external_id = payment.external_id if payment else None

    # Создаём заявку
    return_request = ReturnRequest(
        order_id=order_id,
        user_id=user_id,
        reason=reason,
        comment=comment,
        status="pending",
        payment_external_id=payment_external_id,
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


async def process_refund(db: AsyncSession, return_request: ReturnRequest) -> None:
    """Делает возврат денег по заявке. С защитой от ошибок."""
    # Защита от повторного возврата — ПЕРВОЙ проверкой
    if return_request.status == "refunded":
        raise ReturnError("Деньги по этой заявке уже возвращены")

    if return_request.status != "approved":
        raise ReturnError("Возврат возможен только для одобренной заявки")

    if not return_request.payment_external_id:
        raise ReturnError("Не найден платёж для возврата")

    order = await db.scalar(select(Order).where(Order.id == return_request.order_id))
    if not order:
        raise ReturnError("Заказ не найден")

    # Вызываем возврат в YooKassa
    status = await payment_service.create_refund(
        return_request.payment_external_id, order.total
    )

    # Если возврат успешен — сразу ставим статус (не ждём webhook).
    # Webhook придёт как дополнительное подтверждение.
    if status == "succeeded":
        return_request.status = "refunded"
        await db.commit()
