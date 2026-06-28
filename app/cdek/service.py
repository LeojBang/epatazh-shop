"""
Бизнес-логика СДЭК: передача заказа в систему СДЭК и получение статуса.

Передача заказа создаёт заявку в ИС СДЭК (тариф «склад-склад», ПВЗ→ПВЗ).
В ответ приходит uuid, по которому потом запрашиваем номер и статусы.

Вес товаров: точных весов в каталоге пока нет, поэтому берём оценку
DEFAULT_ITEM_WEIGHT_G на единицу. Позже можно завести вес у товара.
"""

from app.cdek.client import cdek_client, CdekError
from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger("cdek")

# Оценка веса одной единицы товара, граммы (экипировка лёгкая).
DEFAULT_ITEM_WEIGHT_G = 500
# Тариф 136 — «Посылка склад-склад» (ПВЗ → ПВЗ).
TARIFF_PVZ = 136


def _build_packages(order) -> list[dict]:
    """Собирает грузоместо с позициями заказа."""
    items = []
    total_weight = 0
    for it in order.items:
        # вес единицы зафиксирован в заказе; запасной вариант — константа
        weight = getattr(it, "weight", None) or DEFAULT_ITEM_WEIGHT_G
        total_weight += weight * it.quantity
        items.append(
            {
                "name": it.product_name[:255],
                "ware_key": str(it.variant_id or it.product_id)[:50],
                "cost": float(it.price),
                "amount": it.quantity,
                "weight": weight,
                "payment": {"value": 0},  # без наложенного платежа (оплата на сайте)
            }
        )
    return [
        {
            "number": str(order.id)[:30],
            "weight": max(total_weight, DEFAULT_ITEM_WEIGHT_G),
            "items": items,
        }
    ]


async def send_order_to_cdek(order) -> dict | None:
    """
    Регистрирует заказ в СДЭК. Возвращает {'uuid': ...} или None при ошибке.
    Не бросает исключение наверх — доставку нельзя «уронить» из-за СДЭК,
    менеджер сможет передать заказ вручную из админки.
    """
    if order.delivery_type != "pvz" or not order.cdek_pvz_code:
        logger.info("Заказ %s не для ПВЗ или нет кода пункта — пропуск СДЭК", order.id)
        return None

    payload = {
        "type": 1,  # интернет-магазин
        "tariff_code": TARIFF_PVZ,
        "number": str(order.id)[:30],
        "from_location": {"code": settings.CDEK_SENDER_CITY_CODE},
        "delivery_point": order.cdek_pvz_code,
        "recipient": {
            "name": order.full_name,
            "phones": [{"number": order.phone}],
            "email": order.email,
        },
        "sender": {"name": settings.PROJECT_NAME},
        "packages": _build_packages(order),
    }

    try:
        resp = await cdek_client.create_order(payload)
    except CdekError as e:
        logger.error("Не удалось передать заказ %s в СДЭК: %s", order.id, e)
        return None

    entity = (resp or {}).get("entity") or {}
    uuid = entity.get("uuid")
    if uuid:
        logger.info("Заказ %s передан в СДЭК, uuid=%s", order.id, uuid)
        return {"uuid": uuid}

    logger.warning("СДЭК не вернул uuid для заказа %s: %s", order.id, resp)
    return None


def _fmt_date(raw: str | None) -> str | None:
    """ISO-дату СДЭК (2026-06-28T12:50:02+0000) → '28.06.2026 15:50'."""
    if not raw:
        return None
    from datetime import datetime

    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%d.%m.%Y %H:%M")
        except (ValueError, TypeError):
            continue
    return raw  # не распарсили — отдаём как есть


async def get_tracking(cdek_uuid: str) -> dict | None:
    """
    Возвращает информацию по заказу из СДЭК: номер, текущий статус, история.
    Формат удобен для шаблона отслеживания.
    """
    try:
        resp = await cdek_client.get_order(cdek_uuid)
    except CdekError as e:
        logger.error("Не удалось получить статус заказа %s: %s", cdek_uuid, e)
        return None

    entity = (resp or {}).get("entity") or {}
    statuses = entity.get("statuses") or []
    # statuses идут от новых к старым; берём текущий (первый)
    current = statuses[0] if statuses else {}
    history = [
        {
            "name": s.get("name"),
            "date": _fmt_date(s.get("date_time")),
            "city": s.get("city"),
        }
        for s in statuses
    ]
    return {
        "cdek_number": entity.get("cdek_number"),
        "current_status": current.get("name"),
        "current_date": _fmt_date(current.get("date_time")),
        "history": history,
    }


async def calculate_delivery(to_city_code: int, items: list[dict]) -> dict | None:
    """
    Считает стоимость и срок доставки в пункт выдачи (тариф 136).

    items — список словарей {"weight": граммы, "quantity": шт}.
    Возвращает {"price": int, "period_min": int, "period_max": int} или None.

    Несколько товаров считаем единой коробкой (одно грузоместо),
    вес = сумма весов всех единиц.
    """
    total_weight = sum(
        (it.get("weight") or DEFAULT_ITEM_WEIGHT_G) * it.get("quantity", 1)
        for it in items
    )
    total_weight = max(total_weight, DEFAULT_ITEM_WEIGHT_G)

    payload = {
        "type": 1,  # интернет-магазин
        "tariff_code": TARIFF_PVZ,
        "from_location": {"code": settings.CDEK_SENDER_CITY_CODE},
        "to_location": {"code": to_city_code},
        "packages": [{"weight": total_weight}],
    }

    try:
        resp = await cdek_client.calculate_tariff(payload)
    except CdekError as e:
        logger.warning("Не удалось рассчитать доставку в город %s: %s", to_city_code, e)
        return None

    if not resp or resp.get("total_sum") is None:
        logger.info("СДЭК не вернул стоимость для города %s: %s", to_city_code, resp)
        return None

    return {
        "price": int(round(float(resp["total_sum"]))),
        "period_min": resp.get("period_min"),
        "period_max": resp.get("period_max"),
    }
