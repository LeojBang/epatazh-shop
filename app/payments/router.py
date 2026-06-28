from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.payments import service as payment_service
from app.core.logging_config import get_logger

logger = get_logger("webhook")

router = APIRouter(tags=["payments"])


@router.post("/payments/webhook")
async def yookassa_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "bad request"}, status_code=400)

    event = body.get("event", "")
    obj = body.get("object", {})

    # Возврат денег подтверждён — отмечаем заявку как refunded
    if event == "refund.succeeded":
        payment_id = obj.get("payment_id")
        logger.info("Webhook YooKassa: возврат по платежу %s", payment_id)
        if payment_id:
            await payment_service.mark_refunded(db, payment_id)
        return JSONResponse({"status": "ok"}, status_code=200)

    # Платёж — берём id платежа, статус перепроверяем у YooKassa
    external_id = obj.get("id")
    logger.info("Webhook YooKassa: платёж %s (%s)", external_id, event)
    if not external_id:
        return JSONResponse({"status": "ignored"}, status_code=200)

    payment, just_paid = await payment_service.sync_payment_status(db, external_id)

    # Заказ только что оплачен — шлём письмо «Заказ оплачен»
    if just_paid and payment:
        try:
            from app.core.email import order_paid_email
            from app.models.order import Order

            order = await db.scalar(select(Order).where(Order.id == payment.order_id))
            if order:
                subject, body = order_paid_email(order)
                await request.app.state.arq_pool.enqueue_job(
                    "send_email_task", to=order.email, subject=subject, body=body
                )
        except Exception as e:
            logger.warning("Не удалось поставить письмо об оплате: %s", e)

        # Передаём оплаченный заказ в СДЭК (получаем uuid для отслеживания)
        try:
            from app.cdek import service as cdek_service
            from app.orders import service as orders_service

            order_full = await orders_service.get_order(db, str(payment.order_id))
            if (
                order_full
                and order_full.cdek_pvz_code
                and not order_full.cdek_order_uuid
            ):
                result = await cdek_service.send_order_to_cdek(order_full)
                if result and result.get("uuid"):
                    order_full.cdek_order_uuid = result["uuid"]
                    await db.commit()
        except Exception as e:
            logger.warning("Не удалось передать заказ в СДЭК: %s", e)
    return JSONResponse({"status": "ok"}, status_code=200)
