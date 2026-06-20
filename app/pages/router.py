from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.page import InfoPage
from app.models.user import User
from app.users.dependencies import get_current_user_optional

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/info/{slug}", response_class=HTMLResponse)
async def info_page(
    request: Request,
    slug: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    result = await db.execute(
        select(InfoPage).where(InfoPage.slug == slug, InfoPage.is_published == True)
    )
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Страница не найдена")

    return templates.TemplateResponse(
        request, "pages/info.html", {"page": page, "user": user}
    )