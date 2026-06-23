from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import JSONResponse

from app.catalog import service
from app.core.database import get_db
from app.models.user import User
from app.users.dependencies import get_current_user_optional
from app.web.filters import update_query

router = APIRouter(tags=["catalog"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["update_query"] = update_query


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    category: str | None = None,
    size: str | None = None,
    sort: str = "name",
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    categories = await service.get_categories(db)
    products, total = await service.get_products(
        db, category_slug=category, size=size, sort=sort, page=page
    )

    per_page = 12
    total_pages = (total + per_page - 1) // per_page
    all_sizes = await service.get_available_sizes(db)

    return templates.TemplateResponse(
        request,
        "catalog/index.html",
        {
            "categories": categories,
            "products": products,
            "active_category": category,
            "active_size": size,
            "active_sort": sort,
            "page": page,
            "total_pages": total_pages,
            "all_sizes": all_sizes,
            "user": user,
        },
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

    from app.reviews import service as review_service

    reviews = await review_service.get_approved_reviews(db, str(product.id))
    avg_rating, reviews_count = await review_service.get_rating_summary(
        db, str(product.id)
    )

    # Может ли текущий пользователь оставить отзыв:
    # залогинен, купил товар, ещё не оставлял отзыв
    can_review = False
    if user:
        purchased = await review_service.has_purchased(
            db, str(user.id), str(product.id)
        )
        existing = await review_service.get_existing_review(
            db, str(user.id), str(product.id)
        )
        can_review = purchased and existing is None

    return templates.TemplateResponse(
        request,
        "catalog/product.html",
        {
            "product": product,
            "user": user,
            "reviews": reviews,
            "avg_rating": avg_rating,
            "reviews_count": reviews_count,
            "can_review": can_review,
        },
    )


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = "",
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    products = await service.search_products(db, q.strip()) if q.strip() else []
    categories = await service.get_categories(db)
    return templates.TemplateResponse(
        request,
        "catalog/search.html",
        {"products": products, "query": q, "categories": categories, "user": user},
    )


@router.get("/api/search-suggest")
async def search_suggest(
    q: str = "",
    db: AsyncSession = Depends(get_db),
):
    query = q.strip()
    if len(query) < 2:
        return JSONResponse({"results": []})

    products = await service.search_products(db, query)
    results = []
    for p in products[:6]:  # не больше 6 подсказок
        results.append(
            {
                "name": p.name,
                "slug": p.slug,
                "price": f"{p.price:.0f}",
                "category": p.category.name if p.category else "",
                "image": f"/static/uploads/{p.images[0].path}" if p.images else None,
            }
        )
    return JSONResponse({"results": results})
