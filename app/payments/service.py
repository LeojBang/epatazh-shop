import uuid

from yookassa import Payment as YooPayment, Refund
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment

from app.core.config import settings

# Важно: импорт настраивает SDK (account_id + secret_key) при загрузке модуля
from app.payments import yookassa_client  # noqa: F401
from app.core.logging_config import get_logger

logger = get_logger("payments")


def build_receipt(order_items, email: str, phone: str) -> dict:
    """Собирает фискальный чек из позиций заказа."""
    items = []
    for item in order_items:
        items.append(
            {
                "description": item.product_name[:128],
                "quantity": f"{item.quantity}.00",
                "amount": {"value": f"{item.price:.2f}", "currency": "RUB"},
                "vat_code": settings.RECEIPT_VAT_CODE,
                "payment_mode": "full_prepayment",
                "payment_subject": "commodity",
            }
        )
    customer = {}
    if email:
        customer["email"] = email
    if phone:
        customer["phone"] = phone
    return {"customer": customer, "items": items}


async def create_payment(db: AsyncSession, *, order, return_url: str) -> str:
    """Создаёт платёж в YooKassa с фискальным чеком. Возвращает URL оплаты."""
    # Явно подгружаем позиции заказа для чека (избегаем lazy load в async)
    from app.models.order import OrderItem

    items_result = await db.execute(
        select(OrderItem).where(OrderItem.order_id == order.id)
    )
    order_items = list(items_result.scalars().all())

    payment = Payment(order_id=order.id, amount=order.total, status="pending")
    db.add(payment)
    await db.flush()

    idempotence_key = str(uuid.uuid4())
    yoo_payment = YooPayment.create(
        {
            "amount": {"value": f"{order.total:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": f"Заказ в магазине Эпатаж на {order.total} ₽",
            "receipt": build_receipt(order_items, order.email, order.phone),
            "metadata": {"order_id": str(order.id), "payment_id": str(payment.id)},
        },
        idempotence_key,
    )

    payment.external_id = yoo_payment.id
    payment.status = yoo_payment.status
    logger.info("Создан платёж YooKassa %s для заказа %s", yoo_payment.id, order.id)
    await db.commit()

    return yoo_payment.confirmation.confirmation_url


async def create_refund(payment_external_id: str, amount) -> str:
    """Создаёт полный возврат в YooKassa по успешному платежу.

    Для полного возврата YooKassa сама сформирует чек возврата
    из данных исходного платежа — передавать receipt не нужно.
    Возвращает статус возврата.
    """
    idempotence_key = str(uuid.uuid4())
    refund = Refund.create(
        {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "payment_id": payment_external_id,
        },
        idempotence_key,
    )
    logger.info(
        "Создан возврат YooKassa %s по платежу %s на сумму %s",
        refund.id,
        payment_external_id,
        amount,
    )
    return refund.status


async def sync_payment_status(
    db: AsyncSession, external_id: str
) -> tuple[Payment | None, bool]:
    """Запрашивает статус платежа у YooKassa, обновляет запись + заказ.

    Возвращает (payment, just_paid), где just_paid=True, если заказ
    ТОЛЬКО ЧТО перешёл в paid (для отправки письма ровно один раз).
    """
    result = await db.execute(select(Payment).where(Payment.external_id == external_id))
    payment = result.scalar_one_or_none()
    if not payment:
        return None, False

    yoo_payment = YooPayment.find_one(external_id)
    payment.status = yoo_payment.status

    just_paid = False
    if yoo_payment.status == "succeeded":
        from app.models.order import Order

        order_result = await db.execute(
            select(Order).where(Order.id == payment.order_id)
        )
        order = order_result.scalar_one_or_none()
        if order and order.status != "paid":
            # Переход из не-paid в paid — это «только что оплачен»
            order.status = "paid"
            just_paid = True
            logger.info("Заказ %s оплачен (платёж %s)", payment.order_id, external_id)

    await db.commit()
    return payment, just_paid


async def mark_refunded(db: AsyncSession, payment_external_id: str) -> None:
    """По id платежа находит заявку на возврат и отмечает деньги возвращёнными."""
    from app.models.return_request import ReturnRequest

    return_request = await db.scalar(
        select(ReturnRequest).where(
            ReturnRequest.payment_external_id == payment_external_id,
            ReturnRequest.status.in_(["approved", "refunded"]),
        )
    )
    if not return_request:
        logger.info(
            "Webhook возврата: заявка для платежа %s не найдена (возможно, уже обработана)",
            payment_external_id,
        )
        return

    if return_request.status == "refunded":
        # Уже отмечено (мы ставим статус сразу после create_refund) — webhook подтверждает
        logger.info(
            "Webhook возврата: заявка %s уже refunded, подтверждено", return_request.id
        )
        return

    return_request.status = "refunded"
    await db.commit()
    logger.info(
        "Заявка на возврат %s отмечена refunded (платёж %s)",
        return_request.id,
        payment_external_id,
    )
