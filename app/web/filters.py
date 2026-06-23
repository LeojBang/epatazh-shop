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


def plural_ru(number: int, one: str, few: str, many: str) -> str:
    """Склоняет слово по числу: 1 товар, 2 товара, 5 товаров."""
    n = abs(number) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def return_status_ru(status: str) -> str:
    """Статус заявки на возврат на русском."""
    mapping = {
        "pending": "На рассмотрении",
        "approved": "Одобрена",
        "rejected": "Отклонена",
        "refunded": "Деньги возвращены",
    }
    return mapping.get(status, status)


def update_query(request, **kwargs):
    """Берёт текущие query-параметры и обновляет заданные, сохраняя остальные.

    None-значение убирает параметр. Возвращает путь с новой query-строкой.
    """
    params = dict(request.query_params)
    for key, value in kwargs.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = str(value)
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{request.url.path}?{query}" if query else request.url.path
