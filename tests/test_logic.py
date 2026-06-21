from decimal import Decimal

from app.web.filters import plural_ru, order_status_ru


class TestPluralRu:
    """Тесты русского склонения числительных."""

    def test_one(self):
        assert plural_ru(1, "товар", "товара", "товаров") == "товар"

    def test_few(self):
        assert plural_ru(2, "товар", "товара", "товаров") == "товара"
        assert plural_ru(3, "товар", "товара", "товаров") == "товара"
        assert plural_ru(4, "товар", "товара", "товаров") == "товара"

    def test_many(self):
        assert plural_ru(5, "товар", "товара", "товаров") == "товаров"
        assert plural_ru(11, "товар", "товара", "товаров") == "товаров"
        assert plural_ru(0, "товар", "товара", "товаров") == "товаров"

    def test_tricky_teens(self):
        # 11-14 всегда "товаров", несмотря на окончание 1-4
        assert plural_ru(11, "товар", "товара", "товаров") == "товаров"
        assert plural_ru(12, "товар", "товара", "товаров") == "товаров"
        assert plural_ru(21, "товар", "товара", "товаров") == "товар"  # 21 → товар


class TestOrderStatusRu:
    """Тесты перевода статусов заказа."""

    def test_known_statuses(self):
        assert order_status_ru("paid") == "Оплачен"
        assert order_status_ru("pending") == "Ожидает оплаты"
        assert order_status_ru("cancelled") == "Отменён"

    def test_unknown_status(self):
        # неизвестный статус возвращается как есть
        assert order_status_ru("whatever") == "whatever"