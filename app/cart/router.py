import uuid

import redis.asyncio as redis
from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart import service
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.user import User
from app.users.dependencies import get_current_user_optional

router = APIRouter(tags=["cart"])
templates = Jinja2Templates(directory="app/templates")

GUEST_COOKIE = "guest_id"


def get_user_id(
    user: User | None,
    guest_id: str | None,
) -> tuple[str, str | None]:
    """Возвращает (cart_key_id, new_guest_id_if_created)."""
    if user:
        return str(user.id), None
    if guest_id:
        return f"guest:{guest_id}", None
    new_guest_id = str(uuid.uuid4())
    return f"guest:{new_guest_id}", new_guest_id


@router.get("/cart", response_class=HTMLResponse)
async def cart_page(
    request: Request,
    guest_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
    user: User | None = Depends(get_current_user_optional),
):
    user_id, _ = get_user_id(user, guest_id)
    items, total = await service.get_cart_with_products(r, db, user_id)
    return templates.TemplateResponse(
        request,
        "cart/index.html",
        {"items": items, "total": total, "user": user},
    )


@router.post("/cart/add")
async def add_to_cart(
    variant_id: str = Form(...),
    quantity: int = Form(1),
    product_slug: str = Form(""),
    guest_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
    user: User | None = Depends(get_current_user_optional),
):
    user_id, new_guest_id = get_user_id(user, guest_id)
    result = await service.add_to_cart(r, db, user_id, variant_id, quantity)

    # Возвращаемся на страницу товара с отметкой об успехе/ошибке
    if product_slug:
        ok = "1" if result.get("ok") else "0"
        url = f"/catalog/{product_slug}?added={ok}"
    else:
        url = "/cart"

    response = RedirectResponse(url=url, status_code=303)
    if new_guest_id:
        response.set_cookie(GUEST_COOKIE, new_guest_id, httponly=True, samesite="lax")
    return response


@router.post("/cart/remove")
async def remove_from_cart(
    variant_id: str = Form(...),
    guest_id: str | None = Cookie(default=None),
    r: redis.Redis = Depends(get_redis),
    user: User | None = Depends(get_current_user_optional),
):
    user_id, _ = get_user_id(user, guest_id)
    await service.remove_from_cart(r, user_id, variant_id)
    return RedirectResponse(url="/cart", status_code=303)


@router.post("/cart/update")
async def update_cart(
    variant_id: str = Form(...),
    quantity: int = Form(...),
    guest_id: str | None = Cookie(default=None),
    r: redis.Redis = Depends(get_redis),
    user: User | None = Depends(get_current_user_optional),
):
    user_id, _ = get_user_id(user, guest_id)
    await service.update_quantity(r, user_id, variant_id, quantity)
    return RedirectResponse(url="/cart", status_code=303)
