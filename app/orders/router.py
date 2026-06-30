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
from app.web.filters import order_status_ru, msk_datetime, msk_date, plural_ru

router = APIRouter(tags=["orders"])
templates = Jinja2Templates(directory="app/templates")

templates.env.filters["order_status_ru"] = order_status_ru
templates.env.filters["msk_datetime"] = msk_datetime
templates.env.filters["msk_date"] = msk_date
templates.env.filters["plural_ru"] = plural_ru


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
    delivery_type: str = Form("pvz"),
    cdek_city_code: int | None = Form(None),
    cdek_city_name: str | None = Form(None),
    cdek_pvz_code: str | None = Form(None),
    cdek_pvz_address: str | None = Form(None),
    guest_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
    user: User | None = Depends(get_current_user_optional),
):
    cart_user_id, _ = get_user_id(user, guest_id)

    # Валидация формы
    try:
        form = CheckoutForm(
            email=email,
            phone=phone,
            full_name=full_name,
            address=address,
            delivery_type=delivery_type,
            cdek_city_code=cdek_city_code,
            cdek_city_name=cdek_city_name,
            cdek_pvz_code=cdek_pvz_code,
            cdek_pvz_address=cdek_pvz_address,
        )
    except ValidationError:
        items, total = await cart_service.get_cart_with_products(r, db, cart_user_id)
        return templates.TemplateResponse(
            request,
            "orders/checkout.html",
            {
                "items": items,
                "total": total,
                "user": user,
                "error": "Проверьте правильность заполнения полей",
            },
            status_code=400,
        )

    # Для ПВЗ обязателен выбранный пункт
    if form.delivery_type == "pvz" and not form.cdek_pvz_code:
        items, total = await cart_service.get_cart_with_products(r, db, cart_user_id)
        return templates.TemplateResponse(
            request,
            "orders/checkout.html",
            {
                "items": items,
                "total": total,
                "user": user,
                "error": "Выберите пункт выдачи на карте",
            },
            status_code=400,
        )

    try:
        order = await service.create_order(
            db,
            r,
            cart_user_id,
            user_id=str(user.id) if user else None,
            email=form.email,
            phone=form.phone,
            full_name=form.full_name,
            address=form.address,
            delivery_type=form.delivery_type,
            cdek_city_code=form.cdek_city_code,
            cdek_city_name=form.cdek_city_name,
            cdek_pvz_code=form.cdek_pvz_code,
            cdek_pvz_address=form.cdek_pvz_address,
        )
    except CheckoutError as e:
        items, total = await cart_service.get_cart_with_products(r, db, cart_user_id)
        return templates.TemplateResponse(
            request,
            "orders/checkout.html",
            {"items": items, "total": total, "user": user, "error": str(e)},
            status_code=400,
        )

    # Письмо «Заказ принят» — ставим в фоновую очередь (не тормозим оформление)
    try:
        from app.core.email import order_created_email

        # Перезагружаем заказ с подгруженными позициями (избегаем MissingGreenlet)
        order_full = await service.get_order(db, str(order.id))
        subject, body = order_created_email(order_full)
        await request.app.state.arq_pool.enqueue_job(
            "send_email_task", to=order_full.email, subject=subject, body=body
        )
    except Exception as e:
        from app.core.logging_config import get_logger

        get_logger("email").warning("Не удалось поставить письмо в очередь: %s", e)

        # Формируем URL возврата — сюда YooKassa вернёт покупателя после оплаты
    return_url = str(request.base_url) + f"orders/{order.id}/payment-return"
    payment_url = await payment_service.create_payment(
        db, order=order, return_url=return_url
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
    # Защита от чужого доступа: заказ зарегистрированного пользователя
    # виден только ему. Гостевой заказ (без владельца) доступен по ссылке.
    if order.user_id and (not user or order.user_id != user.id):
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
    # Защита от чужого доступа (см. order_success)
    if order.user_id and (not user or order.user_id != user.id):
        raise HTTPException(status_code=404, detail="Заказ не найден")

    # Находим платёж заказа и спрашиваем у YooKassa актуальный статус
    from sqlalchemy import select
    from app.models.payment import Payment

    result = await db.execute(
        select(Payment)
        .where(Payment.order_id == order_id)
        .order_by(Payment.created_at.desc())
    )
    payment = result.scalars().first()

    if payment and payment.external_id:
        _, just_paid = await payment_service.sync_payment_status(
            db, payment.external_id
        )
        await db.refresh(order)

        # Заказ только что оплачен — письмо «Заказ оплачен»
        if just_paid:
            try:
                from app.core.email import order_paid_email

                subject, body = order_paid_email(order)
                await request.app.state.arq_pool.enqueue_job(
                    "send_email_task", to=order.email, subject=subject, body=body
                )
            except Exception as e:
                from app.core.logging_config import get_logger

                get_logger("email").warning(
                    "Не удалось поставить письмо об оплате: %s", e
                )

            # Передаём оплаченный заказ в СДЭК (резервный путь к вебхуку —
            # срабатывает при возврате покупателя, в т.ч. при локальном тесте)
            try:
                from app.cdek import service as cdek_service

                order_full = await service.get_order(db, str(order.id))
                if (
                    order_full
                    and order_full.cdek_pvz_code
                    and not order_full.cdek_order_uuid
                ):
                    res = await cdek_service.send_order_to_cdek(order_full)
                    if res and res.get("uuid"):
                        order_full.cdek_order_uuid = res["uuid"]
                        await db.commit()
            except Exception as e:
                from app.core.logging_config import get_logger

                get_logger("cdek").warning("Не удалось передать заказ в СДЭК: %s", e)

    return templates.TemplateResponse(
        request, "orders/payment_return.html", {"order": order, "user": user}
    )


@router.get("/account/orders", response_class=HTMLResponse)
async def my_orders(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    all_orders = await service.get_user_orders(db, user.id)

    active_statuses = {"new", "pending", "paid", "shipped"}
    active = [o for o in all_orders if o.status in active_statuses]
    completed = [o for o in all_orders if o.status not in active_statuses]

    return templates.TemplateResponse(
        request,
        "orders/list.html",
        {"orders": all_orders, "active": active, "completed": completed, "user": user},
    )


@router.post("/orders/{order_id}/pay")
async def pay_order(
    request: Request,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = await service.get_order(db, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    if order.status != "pending":
        return RedirectResponse(url="/account/orders", status_code=303)

    return_url = str(request.base_url) + f"orders/{order.id}/payment-return"
    payment_url = await payment_service.create_payment(
        db, order=order, return_url=return_url
    )
    return RedirectResponse(url=payment_url, status_code=303)


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    request: Request,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = await service.get_order(db, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    # Отменить можно только неоплаченный заказ
    if order.status == "pending":
        await service.cancel_order_return_stock(db, order)

    return RedirectResponse(url="/account/orders", status_code=303)


@router.get("/track", response_class=HTMLResponse)
async def track_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    number = request.query_params.get("number", "").strip()

    # Если передан трек-номер и пользователь залогинен — ищем автоматически
    if number and user:
        order = None
        error = None
        tracking = None
        try:
            found = await service.get_order(db, number)
            if found and found.email.lower() == user.email.lower():
                order = found
            else:
                error = "Заказ не найден или принадлежит другому аккаунту."
        except Exception:
            error = "Неверный формат номера заказа."

        if order and order.cdek_order_uuid:
            try:
                from app.cdek import service as cdek_service

                tracking = await cdek_service.get_tracking(order.cdek_order_uuid)
                if (
                    tracking
                    and tracking.get("cdek_number")
                    and not order.cdek_track_number
                ):
                    order.cdek_track_number = tracking["cdek_number"]
                    await db.commit()
            except Exception as e:
                from app.core.logging_config import get_logger

                get_logger("cdek").warning("Не удалось получить статус СДЭК: %s", e)

        return templates.TemplateResponse(
            request,
            "orders/track.html",
            {
                "user": user,
                "order": order,
                "error": error,
                "tracking": tracking,
                "prefill_number": number,
            },
        )

    return templates.TemplateResponse(
        request, "orders/track.html", {"user": user, "prefill_number": number}
    )


@router.post("/track", response_class=HTMLResponse)
async def track_order(
    request: Request,
    order_id: str = Form(...),
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    order = None
    error = None
    tracking = None

    order_id_clean = order_id.strip()
    email_clean = email.strip().lower()

    # Сначала ищем по UUID заказа
    try:
        found = await service.get_order(db, order_id_clean)
        if found and found.email.lower() == email_clean:
            order = found
    except Exception:
        pass

    # Если не нашли по полному UUID — пробуем по короткому номеру (начало UUID)
    if not order:
        try:
            found = await service.find_order_by_short_id(db, order_id_clean)
            if found and found.email.lower() == email_clean:
                order = found
        except Exception:
            pass

    # Если не нашли — пробуем по трек-номеру СДЭК
    if not order:
        try:
            from sqlalchemy import select as sa_select
            from app.models.order import Order
            from sqlalchemy.orm import selectinload

            result = await db.execute(
                sa_select(Order)
                .where(Order.cdek_track_number == order_id_clean)
                .options(selectinload(Order.items))
            )
            found = result.scalar_one_or_none()
            if found and found.email.lower() == email_clean:
                order = found
        except Exception:
            pass

    if not order:
        error = "Заказ с такими данными не найден. Проверьте номер заказа (или трек-номер СДЭК) и email."

    # Если заказ передан в СДЭК — подтянем реальный статус доставки
    if order and order.cdek_order_uuid:
        try:
            from app.cdek import service as cdek_service

            tracking = await cdek_service.get_tracking(order.cdek_order_uuid)
            # Сохраним номер СДЭК в заказ, если ещё не сохранён
            if tracking and tracking.get("cdek_number") and not order.cdek_track_number:
                order.cdek_track_number = tracking["cdek_number"]
                await db.commit()
        except Exception as e:
            from app.core.logging_config import get_logger

            get_logger("cdek").warning("Не удалось получить статус СДЭК: %s", e)

    return templates.TemplateResponse(
        request,
        "orders/track.html",
        {"user": user, "order": order, "error": error, "tracking": tracking},
    )


@router.get("/account/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(
    request: Request,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = await service.get_order(db, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    return templates.TemplateResponse(
        request, "orders/detail.html", {"order": order, "user": user}
    )
