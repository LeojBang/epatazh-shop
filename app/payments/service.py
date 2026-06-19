import uuid

from yookassa import Payment as YooPayment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.payment import Payment

# Важно: импорт настраивает SDK (account_id + secret_key) при загрузке модуля
from app.payments import yookassa_client  # noqa: F401


async def create_payment(
    db: AsyncSession,
    order_id: str,
    amount,
    description: str,
    return_url: str,
) -> str:
    """Создаёт платёж в YooKassa и запись у нас. Возвращает URL страницы оплаты."""
    # 1. Своя запись о платеже (пока без external_id)
    payment = Payment(order_id=order_id, amount=amount, status="pending")
    db.add(payment)
    await db.flush()  # получаем payment.id, но ещё не коммитим

    # 2. Запрос в YooKassa. idempotence_key защищает от двойного списания
    #    при повторной отправке того же запроса (например, при ретрае сети).
    idempotence_key = str(uuid.uuid4())
    yoo_payment = YooPayment.create(
        {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": return_url,
            },
            "description": description,
            "metadata": {"order_id": str(order_id), "payment_id": str(payment.id)},
        },
        idempotence_key,
    )

    # 3. Сохраняем id платежа от YooKassa и его статус
    payment.external_id = yoo_payment.id
    payment.status = yoo_payment.status
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

        order_result = await db.execute(select(Order).where(Order.id == payment.order_id))
        order = order_result.scalar_one_or_none()
        if order:
            order.status = "paid"

    await db.commit()
    return payment
