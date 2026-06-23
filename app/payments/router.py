from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
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

    await payment_service.sync_payment_status(db, external_id)
    return JSONResponse({"status": "ok"}, status_code=200)
