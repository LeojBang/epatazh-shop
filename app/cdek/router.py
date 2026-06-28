"""
API-эндпоинты СДЭК для фронтенда (страница оформления заказа).

Браузер обращается сюда, а сервер уже ходит в СДЭК через cdek_client —
так ключи API остаются на сервере и не попадают в браузер.

Эндпоинты:
  GET /api/cdek/cities?q=...        — подсказки городов при вводе
  GET /api/cdek/points?city_code=.. — список ПВЗ в городе (для карты)
"""

from fastapi import APIRouter, Query, Depends, Cookie
from fastapi.responses import JSONResponse
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.cdek.client import cdek_client, CdekError
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
