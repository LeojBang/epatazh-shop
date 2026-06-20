ORDER_STATUS_RU = {
    "new": "Новый",
    "pending": "Ожидает оплаты",
    "paid": "Оплачен",
    "cancelled": "Отменён",
    "shipped": "Отправлен",
}


def order_status_ru(status: str) -> str:
    return ORDER_STATUS_RU.get(status, status)