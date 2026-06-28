"""
API-эндпоинты СДЭК для фронтенда (страница оформления заказа).

Браузер обращается сюда, а сервер уже ходит в СДЭК через cdek_client —
так ключи API остаются на сервере и не попадают в браузер.

Эндпоинты:
  GET /api/cdek/cities?q=...        — подсказки городов при вводе
  GET /api/cdek/points?city_code=.. — список ПВЗ в городе (для карты)
"""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.cdek.client import cdek_client, CdekError
from app.core.logging_config import get_logger

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
