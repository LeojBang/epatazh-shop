from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service
from app.core.database import get_db
from app.models.user import User
from app.users.dependencies import get_current_user_optional

router = APIRouter(tags=["catalog"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    categories = await service.get_categories(db)
    products = await service.get_products(db, category_slug=category)
    return templates.TemplateResponse(
        request,
        "catalog/index.html",
        {"categories": categories, "products": products, "active_category": category, "user": user},
    )


@router.get("/catalog/{slug}", response_class=HTMLResponse)
async def product_page(
    request: Request,
    slug: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    product = await service.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return templates.TemplateResponse(
        request,
        "catalog/product.html",
        {"product": product, "user": user},
    )