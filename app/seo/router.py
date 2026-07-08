"""
SEO-эндпоинты: robots.txt и sitemap.xml.

robots.txt — инструкция поисковикам (что индексировать).
sitemap.xml — карта сайта (список страниц для быстрой индексации),
генерируется динамически из активных товаров и категорий.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import Response, FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.catalog import Product, Category

router = APIRouter(tags=["seo"])


# Favicon в корне — поисковики и браузеры запрашивают /favicon.ico по умолчанию.
# Статика примонтирована на /static, поэтому корневые пути отдаём явными роутами.
@router.get("/favicon.ico", include_in_schema=False)
async def favicon_ico() -> FileResponse:
    return FileResponse("app/static/favicon.ico", media_type="image/x-icon")


@router.get("/apple-touch-icon.png", include_in_schema=False)
async def apple_touch_icon() -> FileResponse:
    return FileResponse("app/static/apple-touch-icon.png", media_type="image/png")


@router.get("/robots.txt")
async def robots(request: Request) -> Response:
    """Инструкция для поисковых роботов."""
    base = str(request.base_url).rstrip("/")
    # Закрываем от индексации служебные разделы (корзина, ЛК, оформление)
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /cart\n"
        "Disallow: /checkout\n"
        "Disallow: /account\n"
        "Disallow: /login\n"
        "Disallow: /register\n"
        "Disallow: /orders\n"
        "Disallow: /admin\n"
        "Disallow: /api/\n"
        f"\nSitemap: {base}/sitemap.xml\n"
    )
    return Response(content=content, media_type="text/plain")


@router.get("/sitemap.xml")
async def sitemap(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """Карта сайта из статических страниц + товаров + категорий."""
    base = str(request.base_url).rstrip("/")

    # Статические страницы
    urls: list[tuple[str, str]] = [
        (f"{base}/", "1.0"),
        (f"{base}/catalog", "0.9"),
        (f"{base}/info/delivery", "0.5"),
        (f"{base}/info/sizes", "0.5"),
        (f"{base}/info/about", "0.5"),
        (f"{base}/info/contacts", "0.5"),
    ]

    # Товары
    products = await db.execute(select(Product.slug).where(Product.is_active.is_(True)))
    for (slug,) in products.all():
        urls.append((f"{base}/catalog/{slug}", "0.8"))

    # Категории (через фильтр каталога)
    categories = await db.execute(select(Category.slug))
    for (slug,) in categories.all():
        urls.append((f"{base}/catalog?category={slug}", "0.7"))

    # Сборка XML
    items = "\n".join(
        f"  <url><loc>{loc}</loc><priority>{pr}</priority></url>" for loc, pr in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}\n"
        "</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")
