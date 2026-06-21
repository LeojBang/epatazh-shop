from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.service import get_product_by_slug
from app.core.database import get_db
from app.models.user import User
from app.reviews import service
from app.reviews.service import ReviewError
from app.users.dependencies import get_current_user

router = APIRouter(tags=["reviews"])


@router.post("/catalog/{slug}/review")
async def add_review(
    slug: str,
    request: Request,
    rating: int = Form(...),
    text: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    product = await get_product_by_slug(db, slug)
    if not product:
        return RedirectResponse(url="/catalog", status_code=303)

    try:
        await service.create_review(db, str(user.id), str(product.id), rating, text)
    except ReviewError:
        # Отзыв не прошёл проверку — просто возвращаем на страницу товара.
        # (Сообщение об ошибке можно показать через query-параметр, добавим при желании.)
        return RedirectResponse(url=f"/catalog/{slug}?review_error=1", status_code=303)

    return RedirectResponse(url=f"/catalog/{slug}?review_added=1", status_code=303)
