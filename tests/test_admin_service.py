"""
Тесты для app/admin2/service.py — изменения, внесённые перед продом:
  - slug_is_taken(): дедупликация slug при создании/редактировании товара
  - delete_product(): каскадное удаление отзывов, скрытие товара из заказов
"""

import uuid
from decimal import Decimal


from app.admin2 import service
from app.models.catalog import Category, Product, ProductVariant
from app.models.order import Order, OrderItem
from app.models.review import Review


# ─── Вспомогательные хелперы ────────────────────────────────────────────────


async def _make_category(db) -> Category:
    cat = Category(name="Тест", slug=f"cat-{uuid.uuid4().hex[:6]}")
    db.add(cat)
    await db.flush()
    return cat


async def _make_product(db, slug="test-slug", is_active=True) -> Product:
    cat = await _make_category(db)
    p = Product(
        category_id=cat.id,
        name="Тест-товар",
        slug=slug,
        price=Decimal("1000.00"),
        is_active=is_active,
    )
    db.add(p)
    await db.commit()
    # Возвращаем через get_product_for_edit — он загружает variants через
    # selectinload, что нужно для delete_product (избегаем MissingGreenlet)
    return await service.get_product_for_edit(db, p.id)


async def _make_variant(db, product: Product, stock: int = 5) -> ProductVariant:
    v = ProductVariant(product_id=product.id, size="M", stock=stock)
    db.add(v)
    await db.flush()
    return v


async def _make_review(db, product: Product) -> Review:
    r = Review(
        product_id=product.id,
        user_id=uuid.uuid4(),
        rating=5,
        text="Отличный товар",
        is_approved=True,
    )
    db.add(r)
    await db.flush()
    return r


# ─── slug_is_taken ───────────────────────────────────────────────────────────


class TestSlugIsTaken:
    """Проверка уникальности slug при создании и редактировании товара."""

    async def test_free_slug_returns_false(self, db_session):
        """Slug, которого нет в БД — свободен (False)."""
        result = await service.slug_is_taken(db_session, "brand-new-slug")
        assert result is False

    async def test_taken_slug_returns_true(self, db_session):
        """Slug уже занятого товара → True."""
        await _make_product(db_session, slug="already-taken")
        result = await service.slug_is_taken(db_session, "already-taken")
        assert result is True

    async def test_taken_slug_excludes_self(self, db_session):
        """При редактировании товара его собственный slug не считается занятым."""
        product = await _make_product(db_session, slug="my-slug")
        result = await service.slug_is_taken(
            db_session, "my-slug", exclude_id=product.id
        )
        assert result is False

    async def test_taken_slug_still_blocks_another_product(self, db_session):
        """Slug одного товара недоступен для другого, даже с exclude_id."""
        await _make_product(db_session, slug="shared-slug")
        product_b = await _make_product(db_session, slug="other-slug")

        result = await service.slug_is_taken(
            db_session, "shared-slug", exclude_id=product_b.id
        )
        assert result is True

    async def test_slug_check_is_case_sensitive(self, db_session):
        """Проверка чувствительна к регистру."""
        await _make_product(db_session, slug="hoodie")
        result = await service.slug_is_taken(db_session, "Hoodie")
        assert result is False


# ─── delete_product ──────────────────────────────────────────────────────────


class TestDeleteProduct:
    """Удаление товара: каскад отзывов, скрытие при наличии в заказах."""

    async def test_delete_product_without_reviews(self, db_session):
        """Товар без отзывов и заказов удаляется, возвращает True."""
        product = await _make_product(db_session, slug="to-delete")
        result = await service.delete_product(db_session, product)
        assert result is True

        found = await service.get_product_for_edit(db_session, product.id)
        assert found is None

    async def test_delete_product_cascades_reviews(self, db_session):
        """При удалении товара его отзывы удаляются автоматически."""
        product = await _make_product(db_session, slug="with-review")
        review = await _make_review(db_session, product)

        # Перезагружаем с вариантами перед удалением
        product = await service.get_product_for_edit(db_session, product.id)
        result = await service.delete_product(db_session, product)
        assert result is True

        from sqlalchemy import select

        remaining = await db_session.scalar(
            select(Review).where(Review.id == review.id)
        )
        assert remaining is None

    async def test_delete_multiple_reviews(self, db_session):
        """Несколько отзывов одного товара — все удаляются."""
        product = await _make_product(db_session, slug="multi-reviews")
        await _make_review(db_session, product)
        await _make_review(db_session, product)

        from sqlalchemy import select, func

        count_before = await db_session.scalar(
            select(func.count()).where(Review.product_id == product.id)
        )
        assert count_before == 2

        product = await service.get_product_for_edit(db_session, product.id)
        await service.delete_product(db_session, product)

        count_after = await db_session.scalar(
            select(func.count()).where(Review.product_id == product.id)
        )
        assert count_after == 0

    async def test_delete_product_in_orders_hides_instead(self, db_session):
        """Товар с вариантом в заказе нельзя удалить — скрывается (is_active=False)."""
        product = await _make_product(db_session, slug="in-order")
        variant = await _make_variant(db_session, product)

        order = Order(
            status="paid",
            total=Decimal("1000.00"),
            email="t@e.com",
            phone="+79001112233",
            full_name="Тест",
            address="Москва",
        )
        db_session.add(order)
        await db_session.flush()

        item = OrderItem(
            order_id=order.id,
            variant_id=variant.id,
            product_id=product.id,
            product_name="Тест-товар",
            price=Decimal("1000.00"),
            quantity=1,
        )
        db_session.add(item)
        await db_session.flush()

        # delete_product сам делает SELECT ProductVariant + EXISTS OrderItem —
        # не зависит от того, что загружено в объекте product
        result = await service.delete_product(db_session, product)

        assert result is False
        await db_session.refresh(product)
        assert product.is_active is False

    async def test_delete_product_no_variants_in_orders(self, db_session):
        """Товар с вариантом, но без заказов — удаляется нормально."""
        product = await _make_product(db_session, slug="variant-no-order")
        await _make_variant(db_session, product)
        await db_session.commit()

        product = await service.get_product_for_edit(db_session, product.id)
        result = await service.delete_product(db_session, product)
        assert result is True

        found = await service.get_product_for_edit(db_session, product.id)
        assert found is None
