import redis.asyncio as redis
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments import service as payment_service
from app.cart import service as cart_service
from app.cart.router import get_user_id
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.user import User
from app.orders import service
from app.orders.service import CheckoutError
from app.schemas.order import CheckoutForm
from app.users.dependencies import get_current_user, get_current_user_optional

router = APIRouter(tags=["orders"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/checkout", response_class=HTMLResponse)
async def checkout_page(
        request: Request,
        guest_id: str | None = Cookie(default=None),
        db: AsyncSession = Depends(get_db),
        r: redis.Redis = Depends(get_redis),
        user: User | None = Depends(get_current_user_optional),
):
    cart_user_id, _ = get_user_id(user, guest_id)
    items, total = await cart_service.get_cart_with_products(r, db, cart_user_id)

    if not items:
        return RedirectResponse(url="/cart", status_code=303)

    return templates.TemplateResponse(
        request,
        "orders/checkout.html",
        {"items": items, "total": total, "user": user},
    )


@router.post("/checkout")
async def checkout(
        request: Request,
        email: str = Form(...),
        phone: str = Form(...),
        full_name: str = Form(...),
        address: str = Form(...),
        guest_id: str | None = Cookie(default=None),
        db: AsyncSession = Depends(get_db),
        r: redis.Redis = Depends(get_redis),
        user: User | None = Depends(get_current_user_optional),
):
    cart_user_id, _ = get_user_id(user, guest_id)

    # Валидация формы
    try:
        form = CheckoutForm(email=email, phone=phone, full_name=full_name, address=address)
    except ValidationError:
        items, total = await cart_service.get_cart_with_products(r, db, cart_user_id)
        return templates.TemplateResponse(
            request,
            "orders/checkout.html",
            {"items": items, "total": total, "user": user,
             "error": "Проверьте правильность заполнения полей"},
            status_code=400,
        )

    try:
        order = await service.create_order(
            db, r, cart_user_id,
            user_id=str(user.id) if user else None,
            email=form.email,
            phone=form.phone,
            full_name=form.full_name,
            address=form.address,
        )
    except CheckoutError as e:
        items, total = await cart_service.get_cart_with_products(r, db, cart_user_id)
        return templates.TemplateResponse(
            request,
            "orders/checkout.html",
            {"items": items, "total": total, "user": user, "error": str(e)},
            status_code=400,
        )

    # Формируем URL возврата — сюда YooKassa вернёт покупателя после оплаты
    return_url = str(request.base_url) + f"orders/{order.id}/payment-return"

    payment_url = await payment_service.create_payment(
        db,
        order_id=str(order.id),
        amount=order.total,
        description=f"Заказ в магазине на {order.total} ₽",
        return_url=return_url,
    )

    return RedirectResponse(url=payment_url, status_code=303)


@router.get("/orders/{order_id}/success", response_class=HTMLResponse)
async def order_success(
        request: Request,
        order_id: str,
        db: AsyncSession = Depends(get_db),
        user: User | None = Depends(get_current_user_optional),
):
    order = await service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return templates.TemplateResponse(
        request, "orders/success.html", {"order": order, "user": user}
    )


@router.get("/orders/{order_id}/payment-return", response_class=HTMLResponse)
async def payment_return(
        request: Request,
        order_id: str,
        db: AsyncSession = Depends(get_db),
        user: User | None = Depends(get_current_user_optional),
):
    order = await service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    # Находим платёж заказа и спрашиваем у YooKassa актуальный статус
    from sqlalchemy import select
    from app.models.payment import Payment

    result = await db.execute(
        select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc())
    )
    payment = result.scalars().first()

    if payment and payment.external_id:
        await payment_service.sync_payment_status(db, payment.external_id)
        await db.refresh(order)

    return templates.TemplateResponse(
        request, "orders/payment_return.html", {"order": order, "user": user}
    )


@router.get("/account/orders", response_class=HTMLResponse)
async def my_orders(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
):
    orders = await service.get_user_orders(db, str(user.id))
    return templates.TemplateResponse(
        request, "orders/list.html", {"orders": orders, "user": user}
    )
