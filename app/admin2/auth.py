"""Зависимости авторизации для кастомной админки."""

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.users.service import get_user_by_email


async def get_admin_user(
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Проверяет что пользователь залогинен и является суперюзером.
    Не залогинен → 401 (обработчик в main.py редиректит на /login).
    Залогинен, но не админ → 403 (красивая страница).
    """
    # Не залогинен → 401 → редирект на логин (через обработчик в main.py)
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не авторизован",
    )

    if not access_token:
        raise unauthorized

    payload = decode_token(access_token)
    if not payload or payload.get("type") != "access":
        raise unauthorized

    user = await get_user_by_email(db, payload["sub"])
    if not user or not user.is_active:
        raise unauthorized

    # Залогинен, но не суперюзер → 403 (красивая страница «нет доступа»)
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав",
        )

    return user
