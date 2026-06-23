from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.orders import service as order_service
from app.returns import service
from app.returns.service import RETURN_REASONS, ReturnError
from app.users.dependencies import get_current_user
from app.web.filters import (
    order_status_ru,
    msk_datetime,
    msk_date,
    plural_ru,
    return_status_ru,
)

router = APIRouter(tags=["returns"])
templates = Jinja2Templates(directory="app/templates")

templates.env.filters["order_status_ru"] = order_status_ru
templates.env.filters["msk_datetime"] = msk_datetime
templates.env.filters["msk_date"] = msk_date
templates.env.filters["plural_ru"] = plural_ru
templates.env.filters["return_status_ru"] = return_status_ru


@router.get("/account/orders/{order_id}/return", response_class=HTMLResponse)
async def return_form(
    request: Request,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Форма оформления возврата для заказа."""
    order = await order_service.get_order(db, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    return templates.TemplateResponse(
        request,
        "returns/new.html",
        {"order": order, "user": user, "reasons": RETURN_REASONS},
    )


@router.post("/account/orders/{order_id}/return")
async def submit_return(
    request: Request,
    order_id: str,
    reason: str = Form(...),
    comment: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Обработка формы возврата."""
    order = await order_service.get_order(db, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    try:
        await service.create_return_request(
            db,
            order_id=order.id,
            user_id=user.id,
            reason=reason,
            comment=comment.strip() or None,
        )
    except ReturnError as e:
        # Показываем форму снова с ошибкой
        return templates.TemplateResponse(
            request,
            "returns/new.html",
            {
                "order": order,
                "user": user,
                "reasons": RETURN_REASONS,
                "error": str(e),
            },
            status_code=400,
        )

    return RedirectResponse(url="/account/returns", status_code=303)


@router.get("/account/returns", response_class=HTMLResponse)
async def my_returns(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Список заявок на возврат пользователя."""
    returns = await service.get_user_returns(db, user.id)
    return templates.TemplateResponse(
        request,
        "returns/list.html",
        {"returns": returns, "user": user, "reasons": RETURN_REASONS},
    )
