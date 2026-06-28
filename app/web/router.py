from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service as catalog_service
from app.favorites import service as fav_service
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
    featured = await catalog_service.get_featured_products(db, limit=4)

    # Избранное — для подсветки сердечек
    favorite_ids = set()
    if user:
        favorite_ids = await fav_service.get_favorite_ids(db, user.id)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "user": user,
            "categories": categories,
            "featured": featured,
            "favorite_ids": favorite_ids,
        },
    )


# --- Информационные страницы (футер) ---
# slug -> (имя шаблона, заголовок)
_INFO_PAGES = {
    "delivery": ("info/delivery.html", "Доставка и оплата"),
    "return": ("info/return.html", "Обмен и возврат"),
    "sizes": ("info/sizes.html", "Размерная сетка"),
    "about": ("info/about.html", "О компании"),
    "contacts": ("info/contacts.html", "Контакты"),
    "terms": ("info/terms.html", "Пользовательское соглашение"),
    "privacy": ("info/privacy.html", "Политика конфиденциальности"),
    "offer": ("info/offer.html", "Публичная оферта"),
}


@router.get("/info/{slug}", response_class=HTMLResponse)
async def info_page(
    slug: str,
    request: Request,
    user: User | None = Depends(get_current_user_optional),
):
    from fastapi import HTTPException

    page = _INFO_PAGES.get(slug)
    if not page:
        raise HTTPException(status_code=404)
    template_name, title = page
    return templates.TemplateResponse(
        request,
        template_name,
        {"user": user, "page_title": title},
    )
