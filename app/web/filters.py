from datetime import timezone, timedelta

ORDER_STATUS_RU = {
    "new": "Новый",
    "pending": "Ожидает оплаты",
    "paid": "Оплачен",
    "shipped": "Отправлен",
    "delivered": "Доставлен",
    "cancelled": "Отменён",
}

MSK = timezone(timedelta(hours=3))


def order_status_ru(status: str) -> str:
    return ORDER_STATUS_RU.get(status, status)


def msk_datetime(value, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Переводит UTC-время из БД в московское и форматирует."""
    if value is None:
        return ""
    # Если время «наивное» (без пояса) — считаем его UTC
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MSK).strftime(fmt)


def msk_date(value, fmt: str = "%d.%m.%Y") -> str:
    return msk_datetime(value, fmt)
