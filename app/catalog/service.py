import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import Category, Product, ProductVariant, ProductColor


async def get_categories(db: AsyncSession) -> list[Category]:
    result = await db.execute(select(Category).order_by(Category.name))
    return list(result.scalars().all())


async def get_products(
    db: AsyncSession,
    category_slug: str | None = None,
    *,
    size: str | None = None,
    gender: str | None = None,
    sort: str = "name",
    page: int = 1,
    per_page: int = 12,
) -> tuple[list[Product], int]:
    """Возвращает (товары на странице, всего товаров) с фильтрами и пагинацией."""
    query = (
        select(Product)
        .where(Product.is_active)
        .options(
            selectinload(Product.category),
            selectinload(Product.variants),
            selectinload(Product.images),
            selectinload(Product.colors).selectinload(ProductColor.images),
        )
    )

    if category_slug:
        query = query.join(Category).where(Category.slug == category_slug)

    # Фильтр по размеру: товар показываем, если есть вариант этого размера в наличии
    if size:
        query = query.where(
            Product.variants.any(
                (ProductVariant.size == size) & (ProductVariant.stock > 0)
            )
        )

    # Фильтр по полу
    if gender:
        # Унисекс-товары показываем и в мужском, и в женском фильтре
        if gender in ("мужское", "женское"):
            query = query.where(Product.gender.in_([gender, "унисекс"]))
        else:
            query = query.where(Product.gender == gender)

    # Сортировка
    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    elif sort == "new":
        query = query.order_by(Product.created_at.desc())
    else:
        query = query.order_by(Product.name)

    # Считаем общее количество (для пагинации) — до limit/offset

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = await db.scalar(count_query)

    # Пагинация
    page = max(1, page)
    query = query.limit(per_page).offset((page - 1) * per_page)

    result = await db.execute(query)
    return list(result.scalars().all()), total or 0


async def get_product_by_slug(db: AsyncSession, slug: str) -> Product | None:
    result = await db.execute(
        select(Product)
        .where(Product.slug == slug, Product.is_active)
        .options(
            selectinload(Product.category),
            selectinload(Product.variants),
            selectinload(Product.images),
            selectinload(Product.colors).selectinload(ProductColor.images),
        )
    )
    return result.scalar_one_or_none()


async def get_variant(db: AsyncSession, variant_id: str) -> ProductVariant | None:
    # Явно приводим строку к UUID. В PostgreSQL драйвер делает это сам,
    # но явное преобразование надёжнее и работает на любой БД.
    if isinstance(variant_id, str):
        try:
            variant_id = uuid.UUID(variant_id)
        except ValueError:
            return None  # некорректный id — варианта нет

    result = await db.execute(
        select(ProductVariant)
        .where(ProductVariant.id == variant_id)
        .options(selectinload(ProductVariant.product))
    )
    return result.scalar_one_or_none()


async def search_products(db: AsyncSession, query: str) -> list[Product]:
    """Поиск товаров по названию (без учёта регистра)."""
    q = (
        select(Product)
        .where(Product.is_active, Product.name.ilike(f"%{query}%"))
        .options(
            selectinload(Product.category),
            selectinload(Product.variants),
            selectinload(Product.images),
            selectinload(Product.colors).selectinload(ProductColor.images),
        )
        .order_by(Product.name)
    )
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_available_sizes(db: AsyncSession) -> list[str]:
    """Уникальные размеры в каталоге, отсортированные по-человечески."""
    result = await db.execute(
        select(ProductVariant.size).distinct().where(ProductVariant.stock > 0)
    )
    sizes = [row[0] for row in result.all() if row[0]]
    return sort_sizes(sizes)


# Порядок буквенных размеров (от меньшего к большему)
_SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "3XL", "4XL"]


def sort_sizes(sizes: list[str]) -> list[str]:
    """
    Сортирует размеры по-человечески:
    сначала буквенные по росту (XS, S, M, L, XL, XXL),
    затем числовые по возрастанию (28, 30, 32...).
    """

    def key(size: str):
        s = size.strip().upper()
        if s in _SIZE_ORDER:
            return (0, _SIZE_ORDER.index(s), 0)
        # числовой размер
        if s.isdigit():
            return (1, int(s), 0)
        # всё остальное — в конец по алфавиту
        return (2, 0, s)

    return sorted(sizes, key=key)


def filter_sizes_by_gender(sizes: list[str], gender: str | None) -> list[str]:
    """
    Размеры под выбранный пол:
    - детское → только числовые размеры (28, 30, 32...)
    - мужское/женское/унисекс → только буквенные (XS, S, M, L...)
    - пол не выбран → все размеры
    """
    if not gender:
        return sizes
    if gender == "детское":
        return [s for s in sizes if s.strip().isdigit()]
    # взрослые/унисекс — всё, кроме чисто числовых
    return [s for s in sizes if not s.strip().isdigit()]


async def get_featured_products(db: AsyncSession, limit: int = 4) -> list[Product]:
    """Товары для витрины на главной: сначала хиты, потом остальные.

    Отдельно от get_products — главной не нужна пагинация,
    нужен небольшой набор для блока «Популярное».
    """
    # Берём активные товары с бейджем «Хит» в первую очередь
    result = await db.execute(
        select(Product)
        .where(Product.is_active)
        .options(
            selectinload(Product.category),
            selectinload(Product.variants),
            selectinload(Product.images),
            selectinload(Product.colors).selectinload(ProductColor.images),
        )
        .order_by(Product.name)
    )
    products = list(result.scalars().all())

    hits = [p for p in products if p.badge and "хит" in p.badge.lower()]
    featured = hits[:limit] if hits else products[:limit]
    return featured
