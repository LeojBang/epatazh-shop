from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.redis import redis_pool
import redis.asyncio as redis_lib
from fastapi import Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.admin.auth import AdminAuth
from app.admin.views import (
    CategoryAdmin,
    OrderAdmin,
    ProductAdmin,
    ProductVariantAdmin,
    ProductImageAdmin,
    ReviewAdmin,
    UserAdmin,
    DashboardView,
    InfoPageAdmin,
    StockView,
    ReturnRequestAdmin,
)
import app.models  # noqa: F401  — регистрирует все модели в SQLAlchemy
from app.cart.router import router as cart_router
from app.catalog.router import router as catalog_router
from app.core.config import settings
from app.core.database import engine
from app.orders.router import router as orders_router
from app.users.router import router as users_router
from app.web.router import router as web_router
from app.payments.router import router as payments_router
from app.reviews.router import router as reviews_router
from app.pages.router import router as pages_router
from app.returns.router import router as returns_router
from app.favorites.router import router as favorites_router
from app.core.logging_config import setup_logging
from app.core.csrf import CSRF_COOKIE, generate_csrf_token, validate_csrf
from starlette.responses import JSONResponse as StarletteJSON

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Старт: создаём arq-пул для постановки фоновых задач
    app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    yield
    # Остановка: закрываем пул
    pool = getattr(app.state, "arq_pool", None)
    if pool:
        await pool.close()


app = FastAPI(title=settings.PROJECT_NAME, debug=settings.DEBUG, lifespan=lifespan)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Базовые заголовки безопасности на каждый ответ."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # HSTS — только на проде (по HTTP в разработке он бессмыслен/вреден)
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


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
                # Читаем тело и сохраняем, чтобы прочитать заново после проверки
                body = await request.body()

                def make_receive(data):
                    async def receive():
                        return {
                            "type": "http.request",
                            "body": data,
                            "more_body": False,
                        }

                    return receive

                # Возвращаем тело для парсинга формы
                request._receive = make_receive(body)
                # Токен может прийти из формы ИЛИ из заголовка (для AJAX)
                header_token = request.headers.get("X-CSRF-Token")
                if header_token:
                    form_token = header_token
                else:
                    form = await request.form()
                    form_token = form.get("csrf_token")
                if not validate_csrf(request.cookies.get(CSRF_COOKIE), form_token):
                    return StarletteJSON(
                        {
                            "detail": "Ошибка безопасности. Обновите страницу и попробуйте снова."
                        },
                        status_code=403,
                    )

                # Возвращаем тело снова — теперь для роута
                request._receive = make_receive(body)

        response = await call_next(request)

        if is_new:
            response.set_cookie(
                CSRF_COOKIE,
                cookie_token,
                httponly=False,
                samesite="lax",
                secure=settings.ENVIRONMENT != "local",
                max_age=60 * 60 * 24 * 7,
            )

        return response


app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


class CartCountMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Значения по умолчанию — чтобы шаблон не падал, даже если что-то пойдёт не так
        request.state.cart_count = 0
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

                    async with AsyncSessionLocal() as db:
                        user = await get_user_by_email(db, payload["sub"])
                        if user:
                            cart_id = str(user.id)
                            # Счётчик избранного для залогиненного
                            from app.favorites import service as fav_service

                            request.state.favorites_count = (
                                await fav_service.get_favorite_count(db, user.id)
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

        # --- Страницы для футера ---
        try:
            from sqlalchemy import select
            from app.models.page import InfoPage
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(InfoPage)
                    .where(InfoPage.is_published)
                    .order_by(InfoPage.position)
                )
                pages = result.scalars().all()

            footer = {"information": [], "company": [], "legal": []}
            for p in pages:
                if p.footer_group in footer:
                    footer[p.footer_group].append({"slug": p.slug, "title": p.title})
            request.state.footer_pages = footer
        except Exception:
            request.state.footer_pages = {"information": [], "company": [], "legal": []}

        return await call_next(request)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    accept = request.headers.get("accept", "")
    is_html = "text/html" in accept

    # 401 на обычных страницах → отправляем на вход.
    if exc.status_code == status.HTTP_401_UNAUTHORIZED and is_html:
        return RedirectResponse(url="/login", status_code=303)

    # 404 на страницах → красивая страница
    if exc.status_code == status.HTTP_404_NOT_FOUND and is_html:
        from app.templates_env import templates

        return templates.TemplateResponse(
            request, "errors/404.html", {}, status_code=404
        )

    # 405 (метод не разрешён) на страницах → тоже показываем 404-страницу
    # (для пользователя это «такой страницы/действия нет»)
    if exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED and is_html:
        from app.templates_env import templates

        return templates.TemplateResponse(
            request, "errors/404.html", {}, status_code=405
        )

    # Остальное — стандартный JSON-ответ
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Логируем полную ошибку для себя (со стектрейсом)
    from app.core.logging_config import get_logger

    get_logger("error").exception(
        "Необработанная ошибка на %s: %s", request.url.path, exc
    )

    accept = request.headers.get("accept", "")
    is_html = "text/html" in accept

    # Пользователю — вежливая страница без технических деталей
    if is_html:
        from app.templates_env import templates

        return templates.TemplateResponse(
            request, "errors/500.html", {}, status_code=500
        )

    # Для API — JSON без деталей
    return JSONResponse({"detail": "Внутренняя ошибка сервера"}, status_code=500)


app.add_middleware(CartCountMiddleware)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(web_router)
app.include_router(users_router)
app.include_router(catalog_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(payments_router)
app.include_router(pages_router)
app.include_router(reviews_router)
app.include_router(returns_router)
app.include_router(favorites_router)

# --- Админка ---
admin = Admin(
    app, engine, authentication_backend=AdminAuth(secret_key=settings.SECRET_KEY)
)
admin.add_view(UserAdmin)
admin.add_view(CategoryAdmin)
admin.add_view(ProductAdmin)
admin.add_view(OrderAdmin)
admin.add_view(ProductVariantAdmin)
admin.add_view(ProductImageAdmin)
admin.add_view(ReviewAdmin)
admin.add_view(DashboardView)
admin.add_view(InfoPageAdmin)
admin.add_view(StockView)
admin.add_view(ReturnRequestAdmin)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
