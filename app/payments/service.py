import uuid

from yookassa import Payment as YooPayment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment

from app.core.config import settings

# Важно: импорт настраивает SDK (account_id + secret_key) при загрузке модуля
from app.payments import yookassa_client  # noqa: F401
from app.core.logging_config import get_logger

logger = get_logger("payments")


def build_receipt(order, email: str, phone: str) -> dict:
    """Собирает фискальный чек (54-ФЗ) из позиций заказа.

    Сумма позиций чека должна совпадать с суммой платежа до копейки,
    иначе YooKassa отклонит чек.
    """
    items = []
    for item in order.items:
        items.append(
            {
                "description": item.product_name[:128],  # ограничение длины в чеке
                "quantity": f"{item.quantity}.00",
                "amount": {
                    "value": f"{item.price:.2f}",  # цена продажи (с учётом скидки)
                    "currency": "RUB",
                },
                "vat_code": settings.RECEIPT_VAT_CODE,
                "payment_mode": "full_prepayment",
                "payment_subject": "commodity",
            }
        )

    # Контакт покупателя — на него YooKassa пришлёт чек.
    # Достаточно email или телефона.
    customer = {}
    if email:
        customer["email"] = email
    if phone:
        customer["phone"] = phone

    return {"customer": customer, "items": items}


async def create_payment(
    db: AsyncSession,
    *,
    order,
    return_url: str,
) -> str:
    """Создаёт платёж в YooKassa с фискальным чеком. Возвращает URL оплаты."""
    payment = Payment(order_id=order.id, amount=order.total, status="pending")
    db.add(payment)
    await db.flush()

    idempotence_key = str(uuid.uuid4())
    yoo_payment = YooPayment.create(
        {
            "amount": {"value": f"{order.total:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": return_url,
            },
            "description": f"Заказ в магазине Эпатаж на {order.total} ₽",
            "receipt": build_receipt(order, order.email, order.phone),
            "metadata": {"order_id": str(order.id), "payment_id": str(payment.id)},
        },
        idempotence_key,
    )

    payment.external_id = yoo_payment.id
    payment.status = yoo_payment.status
    logger.info("Создан платёж YooKassa %s для заказа %s", yoo_payment.id, order.id)
    await db.commit()

    return yoo_payment.confirmation.confirmation_url


async def sync_payment_status(db: AsyncSession, external_id: str) -> Payment | None:
    """Запрашивает актуальный статус платежа у YooKassa и обновляет нашу запись + заказ."""
    result = await db.execute(select(Payment).where(Payment.external_id == external_id))
    payment = result.scalar_one_or_none()
    if not payment:
        return None

    yoo_payment = YooPayment.find_one(external_id)
    payment.status = yoo_payment.status

    # Если оплата прошла — переводим заказ в paid
    if yoo_payment.status == "succeeded":
        from app.models.order import Order

        order_result = await db.execute(
            select(Order).where(Order.id == payment.order_id)
        )
        order = order_result.scalar_one_or_none()
        if order:
            order.status = "paid"
            logger.info("Заказ %s оплачен (платёж %s)", payment.order_id, external_id)

    await db.commit()
    return payment
