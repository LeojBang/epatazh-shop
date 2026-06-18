from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import Category, Product


async def get_categories(db: AsyncSession) -> list[Category]:
    result = await db.execute(select(Category).order_by(Category.name))
    return list(result.scalars().all())


async def get_products(
    db: AsyncSession,
    category_slug: str | None = None,
) -> list[Product]:
    query = (
        select(Product)
        .where(Product.is_active == True)
        .options(selectinload(Product.category))
        .order_by(Product.name)
    )
    if category_slug:
        query = query.join(Category).where(Category.slug == category_slug)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_product_by_slug(db: AsyncSession, slug: str) -> Product | None:
    result = await db.execute(
        select(Product)
        .where(Product.slug == slug, Product.is_active == True)
        .options(selectinload(Product.category))
    )
    return result.scalar_one_or_none()