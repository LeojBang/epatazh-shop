import secrets

from itsdangerous import URLSafeSerializer, BadSignature

from app.core.config import settings

CSRF_COOKIE = "csrf_token"
_serializer = URLSafeSerializer(settings.SECRET_KEY, salt="csrf")


def generate_csrf_token() -> str:
    """Генерирует случайный токен и подписывает его."""
    raw = secrets.token_urlsafe(32)
    return _serializer.dumps(raw)


def validate_csrf(cookie_token: str | None, form_token: str | None) -> bool:
    """Проверяет, что токен из формы совпадает с токеном из cookie и подпись валидна."""
    if not cookie_token or not form_token:
        return False
    if not secrets.compare_digest(cookie_token, form_token):
        return False
    # Проверяем, что подпись наша (не подделана)
    try:
        _serializer.loads(form_token)
    except BadSignature:
        return False
    return True
