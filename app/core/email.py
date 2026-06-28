import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger("email")


def _fmt_price(value) -> str:
    """Цену 2680 → '2 680 ₽' (пробел-разделитель тысяч)."""
    try:
        rub = int(round(float(value)))
    except (TypeError, ValueError):
        return f"{value} ₽"
    s = str(rub)
    parts = []
    while s:
        parts.insert(0, s[-3:])
        s = s[:-3]
    return "\u00a0".join(parts) + " ₽"


def _short_id(order) -> str:
    """Короткий номер заказа (первые 8 символов UUID, заглавными)."""
    return str(order.id)[:8].upper()


def send_email(to: str, subject: str, body: str) -> None:
    """Отправляет письмо. Если EMAILS_ENABLED=False — только логирует.

    Вызывается из фонового воркера, чтобы не блокировать запрос.
    """
    # В разработке (или если почта не настроена) — просто логируем
    if not settings.EMAILS_ENABLED:
        logger.info(
            "ПИСЬМО (не отправлено, EMAILS_ENABLED=False)\nКому: %s\nТема: %s\n%s",
            to,
            subject,
            body,
        )
        return

    # Реальная отправка через SMTP (Яндекс)
    message = EmailMessage()
    from_addr = settings.SMTP_FROM or settings.SMTP_USER
    if settings.SMTP_FROM_NAME:
        message["From"] = formataddr((settings.SMTP_FROM_NAME, from_addr))
    else:
        message["From"] = from_addr
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
        logger.info("Письмо отправлено: %s (%s)", to, subject)
    except Exception as e:
        # Не роняем процесс из-за письма — логируем ошибку
        logger.error("Ошибка отправки письма %s: %s", to, e)


def order_created_email(order) -> tuple[str, str]:
    """Письмо «Заказ принят». Возвращает (тема, тело)."""
    num = _short_id(order)
    lines = [
        f"Здравствуйте, {order.full_name}!",
        "",
        f"Ваш заказ № {num} принят и ожидает оплаты.",
        f"Сумма: {_fmt_price(order.total)}",
        "",
        "Состав заказа:",
    ]
    for item in order.items:
        size = f", размер {item.size}" if item.size else ""
        lines.append(
            f"  • {item.product_name}{size} — "
            f"{item.quantity} шт. × {_fmt_price(item.price)}"
        )
    lines += [
        "",
        "Как только оплата пройдёт, мы начнём собирать заказ",
        "и пришлём подтверждение с данными пункта выдачи.",
        "",
        "Спасибо, что выбрали «Эпатаж»!",
    ]
    return f"Заказ № {num} принят — Эпатаж", "\n".join(lines)


def order_paid_email(order) -> tuple[str, str]:
    """Письмо «Заказ оплачен». Возвращает (тема, тело)."""
    num = _short_id(order)
    lines = [
        f"Здравствуйте, {order.full_name}!",
        "",
        f"Оплата заказа № {num} на сумму {_fmt_price(order.total)} прошла успешно.",
        "Мы начали собирать ваш заказ.",
    ]

    # Данные пункта выдачи СДЭК — куда придёт посылка
    if order.cdek_pvz_address:
        lines += [
            "",
            "Пункт выдачи СДЭК:",
        ]
        if order.cdek_city_name:
            lines.append(f"  Город: {order.cdek_city_name}")
        lines.append(f"  Адрес: {order.cdek_pvz_address}")
        lines += [
            "",
            "Доставка бесплатная. Когда посылка поступит в пункт выдачи,",
            "СДЭК пришлёт уведомление.",
        ]

    if order.cdek_track_number:
        lines += [
            "",
            f"Трек-номер СДЭК: {order.cdek_track_number}",
        ]

    lines += [
        "",
        "Отследить заказ можно на сайте в разделе «Отследить заказ»",
        f"по номеру № {num} и вашему email.",
        "",
        "Спасибо, что выбрали «Эпатаж»!",
    ]
    return f"Заказ № {num} оплачен — Эпатаж", "\n".join(lines)
