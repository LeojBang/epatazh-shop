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
        weight = DEFAULT_ITEM_WEIGHT_G
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
            "date": s.get("date_time"),
            "city": s.get("city"),
        }
        for s in statuses
    ]
    return {
        "cdek_number": entity.get("cdek_number"),
        "current_status": current.get("name"),
        "current_date": current.get("date_time"),
        "history": history,
    }
