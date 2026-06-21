from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.users.service import get_user_by_email


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = form.get("username", "")
        password = form.get("password", "")

        from app.core.database import AsyncSessionLocal
        from app.core.security import create_access_token
        from app.users.service import authenticate_user

        async with AsyncSessionLocal() as db:
            user = await authenticate_user(db, email, password)

        # Пускаем только активных суперпользователей
        if not user or not user.is_active or not user.is_superuser:
            return False

        # Кладём тот же access_token, что использует весь сайт
        token = create_access_token(subject=user.email)
        request.session.update({"token": token})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        # Токен может быть либо в сессии админки (вход через форму /admin/login),
        # либо в cookie сайта (если уже залогинен на сайте как админ)
        token = request.session.get("token") or request.cookies.get("access_token")
        if not token:
            return False

        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            return False

        async with AsyncSessionLocal() as db:
            user = await get_user_by_email(db, payload["sub"])

        return bool(user and user.is_active and user.is_superuser)
