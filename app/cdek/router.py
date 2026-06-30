"""
API-эндпоинты СДЭК для фронтенда (страница оформления заказа).

Браузер обращается сюда, а сервер уже ходит в СДЭК через cdek_client —
так ключи API остаются на сервере и не попадают в браузер.

Эндпоинты:
  GET /api/cdek/cities?q=...        — подсказки городов при вводе
  GET /api/cdek/points?city_code=.. — список ПВЗ в городе (для карты)
"""

from fastapi import APIRouter, Query, Depends, Cookie, Request
from fastapi.responses import JSONResponse, Response
import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cdek.client import cdek_client, CdekError
from app.core.config import settings
from app.models.order import Order
from app.cdek import service as cdek_service
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.logging_config import get_logger
from app.cart import service as cart_service
from app.cart.router import get_user_id
from app.models.user import User
from app.users.dependencies import get_current_user_optional

logger = get_logger("cdek")

router = APIRouter(prefix="/api/cdek", tags=["cdek"])


@router.get("/cities")
async def cities(q: str = Query("", min_length=0)):
    """Подсказки городов по части названия (для автодополнения)."""
    q = q.strip()
    if len(q) < 2:
        return JSONResponse({"cities": []})
    try:
        found = await cdek_client.find_cities(q, limit=10)
    except CdekError:
        # Не валим страницу оформления — просто отдаём пусто
        return JSONResponse({"cities": [], "error": "Сервис доставки недоступен"})
    return JSONResponse({"cities": found})


@router.get("/points")
async def points(city_code: int = Query(..., gt=0)):
    """Список пунктов выдачи в городе (для отображения на карте)."""
    try:
        pts = await cdek_client.get_delivery_points(city_code)
    except CdekError:
        return JSONResponse({"points": [], "error": "Сервис доставки недоступен"})
    return JSONResponse({"points": pts})


@router.get("/calculate")
async def calculate(
    city_code: int = Query(..., gt=0),
    guest_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
    user: User | None = Depends(get_current_user_optional),
):
    """Стоимость и срок доставки в выбранный город (по текущей корзине)."""
    cart_user_id, _ = get_user_id(user, guest_id)
    items, _ = await cart_service.get_cart_with_products(r, db, cart_user_id)
    if not items:
        return JSONResponse({"ok": False, "error": "Корзина пуста"})

    # элементы корзины — словари: {"product":..., "quantity":..., ...}
    calc_items = [
        {
            "weight": getattr(it["product"], "weight", None) or 500,
            "quantity": it["quantity"],
        }
        for it in items
    ]
    result = await cdek_service.calculate_delivery(city_code, calc_items)
    if not result:
        return JSONResponse({"ok": False, "error": "Не удалось рассчитать доставку"})
    return JSONResponse({"ok": True, **result})


# ---------------------------------------------------------------------------
# Таблица: числовой status_code СДЭК → статус заказа в магазине.
# Только те коды, которые реально меняют статус.
# Полный список кодов: https://confluence.cdek.ru/pages/viewpage.action?pageId=29934408
# ---------------------------------------------------------------------------
_CDEK_STATUS_MAP: dict[str, str] = {
    # Принят на склад / передан перевозчику → "Отправлен"
    "2": "shipped",  # Принят на склад отправителя
    "3": "shipped",  # Принят на склад СДЭК
    "16": "shipped",  # Выдан на доставку
    "17": "shipped",  # Транзит
    "6": "shipped",  # Передан в доставку
    # Вручён получателю → "Доставлен"
    "4": "delivered",  # Вручён получателю
}


@router.post("/webhook")
async def cdek_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Вебхук от СДЭК: автоматически обновляет статус заказа.
    Управляется флагом CDEK_AUTO_STATUS в .env.
    Если флаг выключен — принимает запрос, логирует, не меняет статус.
    """
    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=200)  # всегда 200, иначе СДЭК будет слать повторно

    event_type = payload.get("type")
    if event_type != "ORDER_STATUS":
        return Response(status_code=200)

    attrs = payload.get("attributes", {})
    cdek_number = attrs.get("cdek_number")  # трек-номер СДЭК
    status_code = str(attrs.get("status_code", ""))
    is_return = attrs.get("is_return", False)

    logger.info(
        "Вебхук СДЭК: cdek_number=%s status_code=%s auto=%s",
        cdek_number,
        status_code,
        settings.CDEK_AUTO_STATUS,
    )

    # Возвраты не трогаем — у них своя логика
    if is_return:
        return Response(status_code=200)

    # Флаг выключен — логируем и выходим
    if not settings.CDEK_AUTO_STATUS:
        logger.info("CDEK_AUTO_STATUS=False — статус не обновляется")
        return Response(status_code=200)

    # Ищем нужный статус в таблице
    new_order_status = _CDEK_STATUS_MAP.get(status_code)
    if not new_order_status:
        return Response(status_code=200)  # код нам неинтересен

    # Находим заказ по трек-номеру СДЭК
    if not cdek_number:
        return Response(status_code=200)

    result = await db.execute(
        select(Order).where(Order.cdek_track_number == cdek_number)
    )
    order = result.scalar_one_or_none()
    if not order:
        logger.warning("Вебхук СДЭК: заказ с трек-номером %s не найден", cdek_number)
        return Response(status_code=200)

    # Не понижаем статус (например не меняем delivered → shipped)
    _STATUS_RANK = {
        "pending": 0,
        "paid": 1,
        "shipped": 2,
        "delivered": 3,
        "cancelled": -1,
    }
    current_rank = _STATUS_RANK.get(order.status, 0)
    new_rank = _STATUS_RANK.get(new_order_status, 0)
    if new_rank <= current_rank:
        return Response(status_code=200)

    order.status = new_order_status
    await db.commit()
    logger.info(
        "Вебхук СДЭК: заказ %s → статус %s (трек %s)",
        str(order.id)[:8].upper(),
        new_order_status,
        cdek_number,
    )
    return Response(status_code=200)
