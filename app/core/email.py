import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger("email")


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
    lines = [
        f"Здравствуйте, {order.full_name}!",
        "",
        f"Ваш заказ на сумму {order.total} ₽ принят и ожидает оплаты.",
        "",
        "Состав заказа:",
    ]
    for item in order.items:
        lines.append(
            f"  • {item.product_name} (размер {item.size}) — "
            f"{item.quantity} шт. × {item.price} ₽"
        )
    lines += [
        "",
        "Спасибо за покупку в магазине «Эпатаж»!",
    ]
    return "Заказ принят — Эпатаж", "\n".join(lines)


def order_paid_email(order) -> tuple[str, str]:
    """Письмо «Заказ оплачен». Возвращает (тема, тело)."""
    body = (
        f"Здравствуйте, {order.full_name}!\n\n"
        f"Оплата заказа на сумму {order.total} ₽ прошла успешно.\n"
        f"Мы начали собирать ваш заказ.\n\n"
        f"Спасибо, что выбрали «Эпатаж»!"
    )
    return "Заказ оплачен — Эпатаж", body
