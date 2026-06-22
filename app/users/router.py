from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.models import User
from app.schemas.user import UserCreate
from app.users import service
from app.users.dependencies import get_current_user
from app.users import rate_limit
from app.core.redis import redis_pool
import redis.asyncio as redis_lib

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

COOKIE_NAME = "access_token"


def _set_auth_cookie(response: RedirectResponse, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT != "local",
    )


@router.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    return templates.TemplateResponse(request, "auth/register.html", {})


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    # Анти-спам: ограничиваем число регистраций с одного IP
    r = redis_lib.Redis(connection_pool=redis_pool)
    ip = rate_limit.get_client_ip(request)
    if await rate_limit.is_blocked(
        r, ip, action="register", max_attempts=rate_limit.REGISTER_MAX
    ):
        await r.aclose()
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "Слишком много регистраций. Попробуйте позже."},
            status_code=429,
        )
    await rate_limit.register_attempt(
        r, ip, action="register", window_seconds=rate_limit.REGISTER_WINDOW_SECONDS
    )
    await r.aclose()

    existing = await service.get_user_by_email(db, email)
    if existing:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "Пользователь с таким email уже существует"},
            status_code=400,
        )

    user = await service.create_user(
        db, UserCreate(email=email, password=password, full_name=full_name or None)
    )
    token = create_access_token(subject=user.email)
    response = RedirectResponse(url="/", status_code=303)
    _set_auth_cookie(response, token)
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse(request, "auth/login.html", {})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    r = redis_lib.Redis(connection_pool=redis_pool)
    # IP клиента (за nginx — из X-Forwarded-For)
    ip = rate_limit.get_client_ip(request)

    # Проверяем блокировку ДО проверки пароля
    if await rate_limit.is_blocked(r, ip):
        await r.aclose()
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Слишком много попыток входа. Попробуйте через 15 минут."},
            status_code=429,
        )

    user = await service.authenticate_user(db, email, password)
    if not user:
        # Неудача — увеличиваем счётчик
        await rate_limit.register_failed_attempt(r, ip)
        await r.aclose()
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Неверный email или пароль"},
            status_code=400,
        )

    # Успех — сбрасываем счётчик и выдаём токен
    await rate_limit.reset_attempts(r, ip)
    await r.aclose()

    token = create_access_token(subject=user.email)
    response = RedirectResponse(url="/", status_code=303)
    _set_auth_cookie(response, token)
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/account", response_class=HTMLResponse)
async def account_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(request, "account/profile.html", {"user": user})


@router.post("/account")
async def update_account(
    request: Request,
    full_name: str = Form(""),
    email: str = Form(...),
    phone: str = Form(""),
    address: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    updated, error = await service.update_profile(
        db, user, full_name=full_name, email=email, phone=phone, address=address
    )
    if error:
        return templates.TemplateResponse(
            request,
            "account/profile.html",
            {"user": user, "error": error},
            status_code=400,
        )

    # Если email сменился, старый JWT (с прежним email в sub) станет невалидным —
    # перевыпускаем токен с новым email
    from app.core.security import create_access_token

    token = create_access_token(subject=updated.email)
    response = RedirectResponse(url="/account?saved=1", status_code=303)
    _set_auth_cookie(response, token)
    return response


@router.post("/account/password")
async def update_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    error = await service.change_password(db, user, current_password, new_password)
    if error:
        return templates.TemplateResponse(
            request,
            "account/profile.html",
            {"user": user, "password_error": error},
            status_code=400,
        )
    return RedirectResponse(url="/account?password_changed=1", status_code=303)
