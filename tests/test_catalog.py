from decimal import Decimal

from app.models.catalog import Product


class TestEffectivePrice:
    """Тесты вычисления цены с учётом скидки."""

    async def test_no_discount(self, db_session):
        """Без скидки — действующая цена равна обычной."""
        product = Product(
            name="Тестовый товар", slug="test-1",
            price=Decimal("3000.00"), is_active=True,
        )
        assert product.effective_price == Decimal("3000.00")

    async def test_with_discount(self, db_session):
        """Со скидкой — действующая цена равна цене со скидкой."""
        product = Product(
            name="Товар со скидкой", slug="test-2",
            price=Decimal("3000.00"), sale_price=Decimal("2400.00"),
            is_active=True,
        )
        assert product.effective_price == Decimal("2400.00")

    async def test_sale_price_higher_ignored(self, db_session):
        """Если sale_price выше обычной — скидка игнорируется (защита от ошибки)."""
        product = Product(
            name="Кривая скидка", slug="test-3",
            price=Decimal("3000.00"), sale_price=Decimal("3500.00"),
            is_active=True,
        )
        # sale_price выше price — это не скидка, берём обычную цену
        assert product.effective_price == Decimal("3000.00")
