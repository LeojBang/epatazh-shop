from decimal import Decimal

from app.cart import service
from app.models.catalog import Category, Product, ProductVariant


class TestCartBasic:
    """Тесты корзины, работающие только с Redis (без базы)."""

    async def test_empty_cart(self, fake_redis):
        """Новая корзина пустая."""
        cart = await service.get_cart(fake_redis, "user1")
        assert cart == {}

    async def test_get_cart_count_empty(self, fake_redis):
        """Счётчик пустой корзины — 0."""
        count = await service.get_cart_count(fake_redis, "user1")
        assert count == 0

    async def test_update_quantity_adds(self, fake_redis):
        """update_quantity задаёт количество варианта."""
        await service.update_quantity(fake_redis, "user1", "variant-a", 3)
        cart = await service.get_cart(fake_redis, "user1")
        assert cart == {"variant-a": 3}

    async def test_update_quantity_zero_removes(self, fake_redis):
        """Количество 0 убирает товар из корзины."""
        await service.update_quantity(fake_redis, "user1", "variant-a", 3)
        await service.update_quantity(fake_redis, "user1", "variant-a", 0)
        cart = await service.get_cart(fake_redis, "user1")
        assert "variant-a" not in cart

    async def test_get_cart_count_sums(self, fake_redis):
        """Счётчик суммирует количества всех вариантов."""
        await service.update_quantity(fake_redis, "user1", "variant-a", 2)
        await service.update_quantity(fake_redis, "user1", "variant-b", 3)
        count = await service.get_cart_count(fake_redis, "user1")
        assert count == 5

    async def test_remove_from_cart(self, fake_redis):
        """remove_from_cart убирает конкретный вариант."""
        await service.update_quantity(fake_redis, "user1", "variant-a", 2)
        await service.update_quantity(fake_redis, "user1", "variant-b", 1)
        await service.remove_from_cart(fake_redis, "user1", "variant-a")
        cart = await service.get_cart(fake_redis, "user1")
        assert cart == {"variant-b": 1}

    async def test_clear_cart(self, fake_redis):
        """clear_cart полностью очищает корзину."""
        await service.update_quantity(fake_redis, "user1", "variant-a", 2)
        await service.clear_cart(fake_redis, "user1")
        cart = await service.get_cart(fake_redis, "user1")
        assert cart == {}

    async def test_carts_are_isolated(self, fake_redis):
        """Корзины разных пользователей не пересекаются."""
        await service.update_quantity(fake_redis, "user1", "variant-a", 2)
        await service.update_quantity(fake_redis, "user2", "variant-b", 5)

        cart1 = await service.get_cart(fake_redis, "user1")
        cart2 = await service.get_cart(fake_redis, "user2")
        assert cart1 == {"variant-a": 2}
        assert cart2 == {"variant-b": 5}


async def _make_product_with_variant(db_session, price="3000.00", sale_price=None, stock=10, size="M"):
    """Хелпер: создаёт категорию, товар и вариант, возвращает вариант."""
    category = Category(name="Тест-категория", slug="test-cat")
    db_session.add(category)
    await db_session.flush()

    product = Product(
        name="Тест-товар", slug="test-prod",
        price=Decimal(price),
        sale_price=Decimal(sale_price) if sale_price else None,
        is_active=True, category_id=category.id,
    )
    db_session.add(product)
    await db_session.flush()

    variant = ProductVariant(product_id=product.id, size=size, stock=stock)
    db_session.add(variant)
    await db_session.commit()
    return variant


class TestAddToCart:
    """Тесты добавления в корзину (Redis + база)."""

    async def test_add_existing_variant(self, fake_redis, db_session):
        """Добавление существующего варианта в наличии работает."""
        variant = await _make_product_with_variant(db_session, stock=10)

        result = await service.add_to_cart(fake_redis, db_session, "user1", str(variant.id), 2)
        assert result["ok"] is True

        cart = await service.get_cart(fake_redis, "user1")
        assert cart[str(variant.id)] == 2

    async def test_add_nonexistent_variant(self, fake_redis, db_session):
        """Несуществующий вариант возвращает ошибку."""
        result = await service.add_to_cart(fake_redis, db_session, "user1", "00000000-0000-0000-0000-000000000000", 1)
        assert result["ok"] is False
        assert "не найден" in result["error"].lower()

    async def test_add_out_of_stock(self, fake_redis, db_session):
        """Вариант с нулевым остатком нельзя добавить."""
        variant = await _make_product_with_variant(db_session, stock=0)

        result = await service.add_to_cart(fake_redis, db_session, "user1", str(variant.id), 1)
        assert result["ok"] is False
        assert "наличии" in result["error"].lower()

    async def test_add_accumulates(self, fake_redis, db_session):
        """Повторное добавление увеличивает количество."""
        variant = await _make_product_with_variant(db_session, stock=10)

        await service.add_to_cart(fake_redis, db_session, "user1", str(variant.id), 1)
        await service.add_to_cart(fake_redis, db_session, "user1", str(variant.id), 2)

        cart = await service.get_cart(fake_redis, "user1")
        assert cart[str(variant.id)] == 3  # 1 + 2


class TestCartWithProducts:
    """Тесты подсчёта корзины с товарами и скидками."""

    async def test_total_without_discount(self, fake_redis, db_session):
        """Сумма считается по обычной цене, когда скидки нет."""
        variant = await _make_product_with_variant(db_session, price="3000.00", stock=10)
        await service.add_to_cart(fake_redis, db_session, "user1", str(variant.id), 2)

        items, total = await service.get_cart_with_products(fake_redis, db_session, "user1")
        assert total == 6000.0  # 3000 × 2
        assert len(items) == 1

    async def test_total_with_discount(self, fake_redis, db_session):
        """Сумма считается по цене со скидкой (effective_price)."""
        variant = await _make_product_with_variant(db_session, price="3000.00", sale_price="2400.00", stock=10)
        await service.add_to_cart(fake_redis, db_session, "user1", str(variant.id), 2)

        items, total = await service.get_cart_with_products(fake_redis, db_session, "user1")
        assert total == 4800.0  # 2400 × 2, НЕ 6000
