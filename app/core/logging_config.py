import logging
import sys


def setup_logging() -> None:
    """Единая настройка логирования для всего приложения."""
    # Формат: время, уровень, откуда, сообщение
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Убираем старые хендлеры, чтобы не было дублей
    root.handlers.clear()
    root.addHandler(handler)

    # Приглушаем шумный SQL-лог (echo от SQLAlchemy) — оставляем только предупреждения
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # uvicorn доступ-логи оставляем как есть
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Получить логгер для модуля."""
    return logging.getLogger(name)