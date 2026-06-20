from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import Category, Product, ProductVariant


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
        .options(
            selectinload(Product.category),
            selectinload(Product.variants),
            selectinload(Product.images),
        )
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
        .options(
            selectinload(Product.category),
            selectinload(Product.variants),
            selectinload(Product.images),
        )
    )
    return result.scalar_one_or_none()


async def get_variant(db: AsyncSession, variant_id: str) -> ProductVariant | None:
    result = await db.execute(
        select(ProductVariant)
        .where(ProductVariant.id == variant_id)
        .options(selectinload(ProductVariant.product))
    )
    return result.scalar_one_or_none()