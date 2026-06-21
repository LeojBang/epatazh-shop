from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service as catalog_service
from app.core.database import get_db
from app.models.user import User
from app.users.dependencies import get_current_user_optional

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    categories = await catalog_service.get_categories(db)
    products = await catalog_service.get_products(db)

    # «Популярное»: сначала товары с бейджем «Хит».
    # Если хитов нет — показываем первые товары как запасной вариант,
    # чтобы блок не пустовал.
    hits = [p for p in products if p.badge and "хит" in p.badge.lower()]
    featured = hits[:4] if hits else products[:4]

    return templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "categories": categories, "featured": featured},
    )
