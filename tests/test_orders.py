from decimal import Decimal

from app.orders import service
from app.models.order import Order, OrderItem


async def _make_order(db_session, user_id=None, status="pending", total="3000.00"):
    """Создаёт заказ с одной позицией напрямую (без create_order)."""
    import uuid

    order = Order(
        user_id=user_id,
        status=status,
        total=Decimal(total),
        email="t@e.com",
        phone="+79001112233",
        full_name="Тест",
        address="Москва",
        items=[
            OrderItem(
                product_id=uuid.uuid4(),  # просто валидный UUID, товар реально не нужен
                product_name="Тест-товар",
                price=Decimal(total),
                quantity=1,
            )
        ],
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


class TestGetOrder:
    """Тесты чтения заказа."""

    async def test_get_existing_order(self, db_session):
        """Существующий заказ находится по id."""
        order = await _make_order(db_session)
        found = await service.get_order(db_session, order.id)
        assert found is not None
        assert found.id == order.id
        assert found.total == Decimal("3000.00")

    async def test_get_order_has_items(self, db_session):
        """У найденного заказа подгружены позиции."""
        order = await _make_order(db_session)
        found = await service.get_order(db_session, order.id)
        assert len(found.items) == 1
        assert found.items[0].product_name == "Тест-товар"


class TestGetUserOrders:
    """Тесты списка заказов пользователя."""

    async def test_user_orders_returned(self, db_session):
        """Возвращаются заказы конкретного пользователя."""
        import uuid

        user_id = uuid.uuid4()
        await _make_order(db_session, user_id=user_id, total="1000.00")
        await _make_order(db_session, user_id=user_id, total="2000.00")

        orders = await service.get_user_orders(db_session, user_id)
        assert len(orders) == 2

    async def test_other_users_orders_excluded(self, db_session):
        """Заказы других пользователей не попадают в список."""
        import uuid

        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        await _make_order(db_session, user_id=user_a)
        await _make_order(db_session, user_id=user_b)

        orders_a = await service.get_user_orders(db_session, user_a)
        assert len(orders_a) == 1
