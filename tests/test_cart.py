from decimal import Decimal

from app.cart import service


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