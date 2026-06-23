from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.users.dependencies import get_current_user
from app.favorites import service

router = APIRouter(tags=["favorites"])
templates = Jinja2Templates(directory="app/templates")


@router.post("/favorites/toggle/{product_id}")
async def toggle(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now_favorite = await service.toggle_favorite(db, user.id, product_id)
    return JSONResponse({"favorite": now_favorite})


@router.get("/account/favorites", response_class=HTMLResponse)
async def favorites_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    products = await service.get_user_favorites(db, user.id)
    favorite_ids = await service.get_favorite_ids(db, user.id)
    return templates.TemplateResponse(
        request,
        "account/favorites.html",
        {"user": user, "products": products, "favorite_ids": favorite_ids},
    )
