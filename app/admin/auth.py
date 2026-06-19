from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.users.service import get_user_by_email


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        # Вход в админку идёт через основную форму /login, отдельной формы не делаем
        return False

    async def logout(self, request: Request) -> bool:
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.cookies.get("access_token")
        if not token:
            return False

        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            return False

        async with AsyncSessionLocal() as db:
            user = await get_user_by_email(db, payload["sub"])

        return bool(user and user.is_active and user.is_superuser)
