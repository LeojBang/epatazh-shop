"""Кастомная админ-панель Эпатаж."""

import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.uploads import save_upload
from app.core.database import get_db
from app.models.user import User
from app.admin2.auth import get_admin_user
from app.admin2 import service
from app.reviews import service as reviews_service

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


async def _base_ctx(db: AsyncSession, admin_user: User, active_section: str) -> dict:
    """Общий контекст для всех страниц админки (счётчики для сайдбара)."""
    from sqlalchemy import select, func
    from app.models.order import Order

    new_orders_count = (
        await db.scalar(select(func.count()).where(Order.status == "new")) or 0
    )
    from app.reviews import service as reviews_service

    pending_reviews_count = await reviews_service.get_pending_count(db)

    from app.models.return_request import ReturnRequest

    pending_returns_count = (
        await db.scalar(
            select(func.count())
            .select_from(ReturnRequest)
            .where(ReturnRequest.status == "pending")
        )
        or 0
    )
    return {
        "admin_user": admin_user,
        "active_section": active_section,
        "new_orders_count": new_orders_count,
        "pending_reviews_count": pending_reviews_count,
        "pending_returns_count": pending_returns_count,
    }


# ─── ГЛАВНАЯ → редирект на товары ────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def admin_index(admin_user: User = Depends(get_admin_user)):
    return RedirectResponse("/admin/products", status_code=302)


# ─── ТОВАРЫ: список ──────────────────────────────────────────────────────────


@router.get("/products", response_class=HTMLResponse)
async def products_list(
    request: Request,
    search: str = "",
    category: str = "",
    status: str = "all",
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    products, total = await service.get_products_list(
        db, search=search, category_slug=category or None, status=status, page=page
    )
    categories = await service.get_categories_list(db)
    ctx = await _base_ctx(db, admin_user, "products")
    return templates.TemplateResponse(
        request,
        "admin/products.html",
        {
            **ctx,
            "products": products,
            "categories": categories,
            "total": total,
            "page": page,
            "per_page": 30,
            "search": search,
            "active_category": category,
            "active_status": status,
        },
    )


# ─── ТОВАРЫ: редактор (создание/редактирование) ───────────────────────────────


@router.get("/products/new", response_class=HTMLResponse)
async def product_new(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    categories = await service.get_categories_list(db)
    ctx = await _base_ctx(db, admin_user, "products")
    return templates.TemplateResponse(
        request,
        "admin/product_edit.html",
        {
            **ctx,
            "product": None,
            "categories": categories,
        },
    )


@router.get("/products/{product_id}/edit", response_class=HTMLResponse)
async def product_edit(
    request: Request,
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    product = await service.get_product_for_edit(db, product_id)
    if not product:
        return RedirectResponse("/admin/products", status_code=302)
    categories = await service.get_categories_list(db)
    ctx = await _base_ctx(db, admin_user, "products")
    return templates.TemplateResponse(
        request,
        "admin/product_edit.html",
        {
            **ctx,
            "product": product,
            "categories": categories,
        },
    )


@router.post("/products/save", response_class=HTMLResponse)
async def product_save(
    request: Request,
    product_id: str = Form(default=""),
    name: str = Form(...),
    slug: str = Form(...),
    category_id: str = Form(...),
    price: str = Form(...),
    sale_price: str = Form(default=""),
    badge: str = Form(default=""),
    gender: str = Form(default=""),
    description: str = Form(default=""),
    material: str = Form(default=""),
    care: str = Form(default=""),
    is_active: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    from decimal import Decimal, InvalidOperation

    # Парсим цены
    try:
        price_val = Decimal(price.replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        price_val = Decimal("0")

    sale_price_val = None
    if sale_price.strip():
        try:
            sale_price_val = Decimal(sale_price.replace(" ", "").replace(",", "."))
        except (InvalidOperation, ValueError):
            pass

    data = {
        "name": name.strip(),
        "slug": slug.strip(),
        "category_id": uuid.UUID(category_id),
        "price": price_val,
        "sale_price": sale_price_val,
        "weight": 500,  # фиксированный вес — клиент не платит за доставку
        "badge": badge.strip() or None,
        "gender": gender.strip() or None,
        "description": description.strip() or None,
        "material": material.strip() or None,
        "care": care.strip() or None,
        "is_active": is_active == "on",
    }

    # Парсим размеры из формы (поля вида size_XS=5)
    form = await request.form()
    sizes_stock = {}
    for key, value in form.items():
        if key.startswith("size_"):
            size_name = key[5:]
            try:
                sizes_stock[size_name] = int(value)
            except ValueError:
                sizes_stock[size_name] = 0

    # Проверяем уникальность slug до INSERT/UPDATE
    existing_id = uuid.UUID(product_id) if product_id else None
    if await service.slug_is_taken(db, data["slug"], exclude_id=existing_id):
        categories = await service.get_categories_list(db)
        ctx = await _base_ctx(db, admin_user, "products")
        product_obj = None
        if product_id:
            product_obj = await service.get_product_for_edit(db, uuid.UUID(product_id))
        return templates.TemplateResponse(
            request,
            "admin/product_edit.html",
            {
                **ctx,
                "product": product_obj,
                "categories": categories,
                "error": f"Slug «{data['slug']}» уже занят другим товаром. Выберите другой slug.",
                "form_data": data,
            },
            status_code=422,
        )

    if product_id:
        product = await service.get_product_for_edit(db, uuid.UUID(product_id))
        if product:
            await service.update_product(db, product, data)
            pid = product.id
    else:
        product = await service.create_product(db, data)
        pid = product.id

    if sizes_stock:
        await service.upsert_variants(db, pid, sizes_stock)

    await db.commit()
    return RedirectResponse(f"/admin/products/{pid}/edit?success=1", status_code=303)


@router.post("/products/{product_id}/delete")
async def product_delete(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    product = await service.get_product_for_edit(db, product_id)
    if product:
        deleted = await service.delete_product(db, product)
        await db.commit()
        if deleted:
            return RedirectResponse("/admin/products?success=deleted", status_code=303)
        else:
            return RedirectResponse("/admin/products?success=hidden", status_code=303)
    await db.commit()
    return RedirectResponse("/admin/products?success=deleted", status_code=303)


# ─── ФОТО ТОВАРА ─────────────────────────────────────────────────────────────


@router.post("/products/{product_id}/images/upload")
async def product_image_upload(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    filename = await save_upload(file)
    if filename:
        await service.add_product_image(db, product_id, filename)
        await db.commit()
    return RedirectResponse(f"/admin/products/{product_id}/edit", status_code=303)


@router.post("/products/{product_id}/images/{image_id}/delete")
async def product_image_delete(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    await service.delete_product_image(db, image_id)
    await db.commit()
    return RedirectResponse(f"/admin/products/{product_id}/edit", status_code=303)


# ─── ЦВЕТА ТОВАРА ────────────────────────────────────────────────────────────


@router.post("/products/{product_id}/colors/save")
async def color_save(
    product_id: uuid.UUID,
    color_id: str = Form(default=""),
    name: str = Form(...),
    hex_code: str = Form(...),
    position: int = Form(default=0),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    cid = uuid.UUID(color_id) if color_id else None
    await service.upsert_color(db, product_id, cid, name, hex_code, position)
    await db.commit()
    return RedirectResponse(f"/admin/products/{product_id}/edit", status_code=303)


@router.post("/products/{product_id}/colors/{color_id}/delete")
async def color_delete(
    product_id: uuid.UUID,
    color_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    await service.delete_color(db, color_id)
    await db.commit()
    return RedirectResponse(f"/admin/products/{product_id}/edit", status_code=303)


@router.post("/products/{product_id}/colors/{color_id}/images/upload")
async def color_image_upload(
    product_id: uuid.UUID,
    color_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    filename = await save_upload(file)
    if filename:
        await service.add_color_image(db, color_id, filename)
        await db.commit()
    return RedirectResponse(f"/admin/products/{product_id}/edit", status_code=303)


@router.post("/products/{product_id}/colors/{color_id}/images/{image_id}/delete")
async def color_image_delete(
    product_id: uuid.UUID,
    color_id: uuid.UUID,
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    await service.delete_color_image(db, image_id)
    await db.commit()
    return RedirectResponse(f"/admin/products/{product_id}/edit", status_code=303)


# ─── КАТЕГОРИИ ───────────────────────────────────────────────────────────────


@router.get("/categories", response_class=HTMLResponse)
async def categories_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    categories = await service.get_categories_list(db)
    ctx = await _base_ctx(db, admin_user, "categories")
    return templates.TemplateResponse(
        request,
        "admin/categories.html",
        {
            **ctx,
            "categories": categories,
        },
    )


@router.post("/categories/save")
async def category_save(
    category_id: str = Form(default=""),
    name: str = Form(...),
    slug: str = Form(...),
    icon: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    data = {"name": name.strip(), "slug": slug.strip(), "icon": icon.strip() or None}
    if category_id:
        cat = await service.get_category(db, uuid.UUID(category_id))
        if cat:
            await service.update_category(db, cat, data)
    else:
        await service.create_category(db, data)
    await db.commit()
    return RedirectResponse("/admin/categories?success=1", status_code=303)


@router.post("/categories/{category_id}/delete")
async def category_delete(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    cat = await service.get_category(db, category_id)
    if cat:
        deleted = await service.delete_category(db, cat)
        await db.commit()
        if not deleted:
            return RedirectResponse(
                "/admin/categories?error=not_empty", status_code=303
            )
    else:
        await db.commit()
    return RedirectResponse("/admin/categories?success=deleted", status_code=303)


# ─── ЗАКАЗЫ ──────────────────────────────────────────────────────────────────


@router.get("/orders", response_class=HTMLResponse)
async def orders_list(
    request: Request,
    status: str = "all",
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    orders, total = await service.get_orders_list(db, status_filter=status, page=page)
    ctx = await _base_ctx(db, admin_user, "orders")
    return templates.TemplateResponse(
        request,
        "admin/orders.html",
        {
            **ctx,
            "orders": orders,
            "total": total,
            "page": page,
            "active_status": status,
            "per_page": 30,
        },
    )


@router.get("/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(
    request: Request,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    order = await service.get_order_detail(db, order_id)
    if not order:
        return RedirectResponse("/admin/orders", status_code=302)
    ctx = await _base_ctx(db, admin_user, "orders")
    return templates.TemplateResponse(
        request,
        "admin/order_detail.html",
        {
            **ctx,
            "order": order,
        },
    )


@router.post("/orders/{order_id}/update")
async def order_update(
    request: Request,
    order_id: uuid.UUID,
    new_status: str = Form(...),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    order = await service.get_order_detail(db, order_id)
    if order:
        old_status = await service.update_order_status(db, order, new_status)
        await db.commit()

        # Письмо покупателю при ключевых сменах статуса
        if new_status != old_status and order.email:
            from app.core import email as email_mod

            builder = {
                "shipped": email_mod.order_shipped_email,
                "cancelled": email_mod.order_cancelled_email,
            }.get(new_status)
            if builder:
                subject, body = builder(order)
                await request.app.state.arq_pool.enqueue_job(
                    "send_email_task", to=order.email, subject=subject, body=body
                )
    return RedirectResponse(f"/admin/orders/{order_id}?success=1", status_code=303)


# ─── ВОЗВРАТЫ ────────────────────────────────────────────────────────────────


@router.get("/returns", response_class=HTMLResponse)
async def returns_list(
    request: Request,
    status: str = "all",
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    returns, total = await service.get_returns_list(db, status_filter=status, page=page)
    ctx = await _base_ctx(db, admin_user, "returns")
    return templates.TemplateResponse(
        request,
        "admin/returns.html",
        {
            **ctx,
            "returns": returns,
            "total": total,
            "page": page,
            "active_status": status,
            "per_page": 30,
        },
    )


@router.get("/returns/{return_id}", response_class=HTMLResponse)
async def return_detail(
    request: Request,
    return_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    ret = await service.get_return_detail(db, return_id)
    if not ret:
        return RedirectResponse("/admin/returns", status_code=302)
    ctx = await _base_ctx(db, admin_user, "returns")
    return templates.TemplateResponse(
        request,
        "admin/return_detail.html",
        {
            **ctx,
            "ret": ret,
        },
    )


@router.post("/returns/{return_id}/update")
async def return_update(
    return_id: uuid.UUID,
    new_status: str = Form(...),
    admin_comment: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    ret = await service.get_return_detail(db, return_id)
    if ret:
        await service.update_return(db, ret, new_status, admin_comment.strip() or None)
    await db.commit()
    return RedirectResponse(f"/admin/returns/{return_id}?success=1", status_code=303)


@router.post("/returns/{return_id}/refund")
async def return_refund(
    return_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    from app.returns import service as returns_service

    ret = await service.get_return_detail(db, return_id)
    if ret and ret.status == "approved":
        try:
            await returns_service.process_refund(db, ret)
            return RedirectResponse(
                f"/admin/returns/{return_id}?success=refunded", status_code=303
            )
        except Exception:
            pass
    await db.commit()
    return RedirectResponse(
        f"/admin/returns/{return_id}?error=refund_failed", status_code=303
    )


# ─── АНАЛИТИКА ───────────────────────────────────────────────────────────────


@router.get("/analytics", response_class=HTMLResponse)
async def analytics(
    request: Request,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    summary = await service.get_analytics_summary(db, days=days)
    ctx = await _base_ctx(db, admin_user, "analytics")
    return templates.TemplateResponse(
        request,
        "admin/analytics.html",
        {
            **ctx,
            **summary,
            "days": days,
        },
    )


# ─── ПОЛЬЗОВАТЕЛИ ────────────────────────────────────────────────────────────


@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    search: str = "",
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    users, total = await service.get_users_list(db, search=search, page=page)
    ctx = await _base_ctx(db, admin_user, "users")
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            **ctx,
            "users": users,
            "total": total,
            "page": page,
            "search": search,
        },
    )


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    target = await service.get_user(db, user_id)
    if not target:
        return RedirectResponse("/admin/users", status_code=302)
    ctx = await _base_ctx(db, admin_user, "users")
    return templates.TemplateResponse(
        request,
        "admin/user_detail.html",
        {
            **ctx,
            "target": target,
        },
    )


@router.post("/users/{user_id}/update")
async def user_update(
    user_id: uuid.UUID,
    full_name: str = Form(default=""),
    is_active: str = Form(default=""),
    is_superuser: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    target = await service.get_user(db, user_id)
    if not target:
        return RedirectResponse("/admin/users", status_code=302)

    new_is_super = is_superuser == "on"
    # Защита: нельзя снять последнего суперюзера
    if target.is_superuser and not new_is_super:
        supers = await service.count_superusers(db)
        if supers <= 1:
            await db.commit()
            return RedirectResponse(
                f"/admin/users/{user_id}?error=last_super", status_code=303
            )

    await service.update_user(
        db,
        target,
        {
            "full_name": full_name.strip() or None,
            "is_active": is_active == "on",
            "is_superuser": new_is_super,
        },
    )
    await db.commit()
    return RedirectResponse(f"/admin/users/{user_id}?success=1", status_code=303)


# ─── ОТЗЫВЫ: модерация ───────────────────────────────────────────────────────


@router.get("/reviews", response_class=HTMLResponse)
async def reviews_list(
    request: Request,
    pending: str = "",
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    only_pending = pending == "1"
    reviews = await reviews_service.get_all_reviews(db, only_pending=only_pending)
    ctx = await _base_ctx(db, admin_user, "reviews")
    ctx.update({"reviews": reviews, "only_pending": only_pending})
    return templates.TemplateResponse(request, "admin/reviews.html", ctx)


@router.post("/reviews/{review_id}/approve")
async def review_approve(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    await reviews_service.approve_review(db, review_id)
    return RedirectResponse("/admin/reviews", status_code=303)


@router.post("/reviews/{review_id}/delete")
async def review_delete(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    await reviews_service.delete_review(db, review_id)
    return RedirectResponse("/admin/reviews", status_code=303)
