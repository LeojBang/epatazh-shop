import redis.asyncio as redis
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

    # Из уведомления берём ТОЛЬКО id платежа. Статусу из тела не доверяем —
    # sync_payment_status сам запросит реальный статус у YooKassa.
    payment_object = body.get("object", {})
    external_id = payment_object.get("id")
    logger.info("Webhook YooKassa: платёж %s", external_id)
    if not external_id:
        return JSONResponse({"status": "ignored"}, status_code=200)

    await payment_service.sync_payment_status(db, external_id)

    # YooKassa ждёт 200 — иначе будет повторять уведомление.
    return JSONResponse({"status": "ok"}, status_code=200)