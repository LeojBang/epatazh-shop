from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.redis import redis_pool
import redis.asyncio as redis_lib
from fastapi import Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.models  # noqa: F401  — регистрирует все модели в SQLAlchemy
from app.cart.router import router as cart_router
from app.catalog.router import router as catalog_router
from app.core.config import settings
from app.orders.router import router as orders_router
from app.users.router import router as users_router
from app.web.router import router as web_router
from app.payments.router import router as payments_router
from app.reviews.router import router as reviews_router
from app.returns.router import router as returns_router
from app.favorites.router import router as favorites_router
from app.cdek.router import router as cdek_router
from app.admin2.router import router as admin_router
from app.core.logging_config import setup_logging
from app.core.csrf import CSRF_COOKIE, generate_csrf_token, validate_csrf
from starlette.responses import JSONResponse as StarletteJSON

setup_logging()

app = FastAPI(title=settings.PROJECT_NAME, debug=settings.DEBUG)


class CSRFMiddleware(BaseHTTPMiddleware):
    # Пути, которые НЕ проверяем (webhook от YooKassa — он внешний, у него нет нашей cookie)
    EXEMPT_PREFIXES = ("/payments/webhook", "/admin")

    async def dispatch(self, request, call_next):
        cookie_token = request.cookies.get(CSRF_COOKIE)
        is_new = False
        if not cookie_token:
            cookie_token = generate_csrf_token()
            is_new = True
        request.state.csrf_token = cookie_token

        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            path = request.url.path
            exempt = any(path.startswith(p) for p in self.EXEMPT_PREFIXES)
            if not exempt:
                # Читаем тело и СОХРАНЯЕМ его, чтобы роут смог прочитать заново
                body = await request.body()

                # Возвращаем тело обратно в поток запроса
                async def receive():
                    return {"type": "http.request", "body": body, "more_body": False}

                request._receive = receive

                # Токен может прийти из заголовка (AJAX) ИЛИ из формы
                header_token = request.headers.get("X-CSRF-Token")
                if header_token:
                    form_token = header_token
                else:
                    # Парсим форму из сохранённого тела для проверки токена
                    form = await request.form()
                    form_token = form.get("csrf_token")
                if not validate_csrf(request.cookies.get(CSRF_COOKIE), form_token):
                    return StarletteJSON(
                        {
                            "detail": "Ошибка безопасности. Обновите страницу и попробуйте снова."
                        },
                        status_code=403,
                    )

                # Ещё раз возвращаем тело — форма выше его снова вычитала
                async def receive2():
                    return {"type": "http.request", "body": body, "more_body": False}

                request._receive = receive2

        response = await call_next(request)

        if is_new:
            response.set_cookie(
                CSRF_COOKIE,
                cookie_token,
                httponly=False,
                samesite="lax",
                max_age=60 * 60 * 24 * 7,
            )

        return response


app.add_middleware(CSRFMiddleware)


class CartCountMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Значения по умолчанию — чтобы шаблон не падал, даже если что-то пойдёт не так
        request.state.cart_count = 0
        request.state.favorites_count = 0
        request.state.footer_pages = {"information": [], "company": [], "legal": []}

        # --- Счётчик корзины ---
        try:
            from app.core.security import decode_token
            from app.cart import service as cart_service

            r = redis_lib.Redis(connection_pool=redis_pool)
            cart_id = None

            access_token = request.cookies.get("access_token")
            if access_token:
                payload = decode_token(access_token)
                if payload and payload.get("type") == "access":
                    from app.core.database import AsyncSessionLocal
                    from app.users.service import get_user_by_email
                    from app.favorites import service as favorites_service

                    async with AsyncSessionLocal() as db:
                        user = await get_user_by_email(db, payload["sub"])
                        if user:
                            cart_id = str(user.id)
                            request.state.favorites_count = (
                                await favorites_service.get_favorite_count(db, user.id)
                            )

            if not cart_id:
                guest_id = request.cookies.get("guest_id")
                if guest_id:
                    cart_id = f"guest:{guest_id}"

            if cart_id:
                request.state.cart_count = await cart_service.get_cart_count(r, cart_id)
            await r.aclose()
        except Exception:
            request.state.cart_count = 0

        return await call_next(request)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # 401 на обычных страницах → отправляем на вход.
    # Для API/JSON-запросов оставляем JSON.
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/login", status_code=303)

    # 403 на страницах → красивая страница вместо голого JSON
    if exc.status_code == status.HTTP_403_FORBIDDEN:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            from app.templates_env import templates

            return templates.TemplateResponse(
                request, "errors/403.html", {}, status_code=403
            )

    # 404 на страницах → красивая страница вместо голого JSON
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            from app.templates_env import templates

            return templates.TemplateResponse(
                request, "errors/404.html", {}, status_code=404
            )

    # Остальное — стандартный JSON-ответ
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


app.add_middleware(CartCountMiddleware)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(web_router)
app.include_router(users_router)
app.include_router(catalog_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(payments_router)
app.include_router(reviews_router)
app.include_router(returns_router)
app.include_router(favorites_router)
app.include_router(cdek_router)
app.include_router(admin_router)

# --- Кастомная админка подключена через admin_router ---


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
