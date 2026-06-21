from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.payments import service
from app.models.order import Order


def make_fake_yoo_payment(payment_id="yoo_test_123", status="pending", url="https://yookassa.test/pay"):
    """Создаёт поддельный ответ YooKassa, как настоящий объект платежа."""
    fake = MagicMock()
    fake.id = payment_id
    fake.status = status
    fake.confirmation.confirmation_url = url
    return fake


class TestCreatePayment:
    """Тесты создания платежа с моком YooKassa."""

    async def test_create_payment_returns_url(self, db_session):
        """create_payment возвращает URL оплаты от YooKassa."""
        # создаём заказ, к которому привяжем платёж
        order = Order(
            status="pending", total=Decimal("3000.00"),
            email="t@e.com", phone="+79001112233",
            full_name="Тест", address="Москва",
        )
        db_session.add(order)
        await db_session.flush()

        fake_payment = make_fake_yoo_payment(url="https://yookassa.test/redirect")

        # подменяем YooPayment.create на мок
        with patch.object(service.YooPayment, "create", return_value=fake_payment) as mock_create:
            url = await service.create_payment(
                db_session, order.id,
                amount=Decimal("3000.00"),
                description="Заказ тест",
                return_url="https://shop.test/return",
            )

        # проверяем: вернулся правильный URL
        assert url == "https://yookassa.test/redirect"
        # проверяем: YooKassa был вызван ровно один раз
        mock_create.assert_called_once()

    async def test_create_payment_saves_external_id(self, db_session):
        """external_id и статус от YooKassa сохраняются в нашу запись."""
        order = Order(
            status="pending", total=Decimal("1500.00"),
            email="t@e.com", phone="+79001112233",
            full_name="Тест", address="Москва",
        )
        db_session.add(order)
        await db_session.flush()

        fake_payment = make_fake_yoo_payment(payment_id="yoo_abc_999", status="pending")

        with patch.object(service.YooPayment, "create", return_value=fake_payment):
            await service.create_payment(
                db_session, order.id,
                amount=Decimal("1500.00"),
                description="Заказ",
                return_url="https://shop.test/return",
            )

        # проверяем, что в базе сохранился external_id от YooKassa
        from sqlalchemy import select
        from app.models.payment import Payment
        result = await db_session.execute(select(Payment).where(Payment.order_id == order.id))
        payment = result.scalar_one()
        assert payment.external_id == "yoo_abc_999"


class TestSyncPaymentStatus:
    """Тесты синхронизации статуса с моком YooKassa."""

    async def test_successful_payment_marks_order_paid(self, db_session):
        """Когда YooKassa говорит 'succeeded' — заказ становится paid."""
        # заказ + платёж
        order = Order(
            status="pending", total=Decimal("2000.00"),
            email="t@e.com", phone="+79001112233",
            full_name="Тест", address="Москва",
        )
        db_session.add(order)
        await db_session.flush()

        from app.models.payment import Payment
        payment = Payment(order_id=order.id, amount=Decimal("2000.00"),
                          status="pending", external_id="yoo_sync_1")
        db_session.add(payment)
        await db_session.flush()

        # YooKassa "отвечает", что платёж успешен
        fake = make_fake_yoo_payment(payment_id="yoo_sync_1", status="succeeded")

        with patch.object(service.YooPayment, "find_one", return_value=fake):
            await service.sync_payment_status(db_session, "yoo_sync_1")

        # проверяем: заказ перешёл в paid
        await db_session.refresh(order)
        assert order.status == "paid"

    async def test_pending_payment_keeps_order_pending(self, db_session):
        """Если платёж ещё pending — заказ остаётся pending."""
        order = Order(
            status="pending", total=Decimal("2000.00"),
            email="t@e.com", phone="+79001112233",
            full_name="Тест", address="Москва",
        )
        db_session.add(order)
        await db_session.flush()

        from app.models.payment import Payment
        payment = Payment(order_id=order.id, amount=Decimal("2000.00"),
                          status="pending", external_id="yoo_sync_2")
        db_session.add(payment)
        await db_session.flush()

        fake = make_fake_yoo_payment(payment_id="yoo_sync_2", status="pending")

        with patch.object(service.YooPayment, "find_one", return_value=fake):
            await service.sync_payment_status(db_session, "yoo_sync_2")

        await db_session.refresh(order)
        assert order.status == "pending"  # не изменился