import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from app.returns import service
from app.returns.service import ReturnError
from app.models.order import Order
from app.models.return_request import ReturnRequest


async def _make_order(db_session, status="paid", total="3000.00", created_at=None):
    """Создаёт оплаченный заказ для тестов возврата."""
    order = Order(
        user_id=uuid.uuid4(),
        status=status,
        total=Decimal(total),
        email="t@e.com",
        phone="+79001112233",
        full_name="Тест",
        address="Москва",
    )
    # Всегда ставим created_at с таймзоной (SQLite иначе теряет tz,
    # и сравнение с aware-датой в проверке срока падает)
    order.created_at = created_at or datetime.now(timezone.utc)
    db_session.add(order)
    await db_session.flush()
    return order


async def _make_return(
    db_session, order, user_id, status="pending", payment_external_id="yoo_pay_1"
):
    """Создаёт заявку на возврат."""
    rr = ReturnRequest(
        order_id=order.id,
        user_id=user_id,
        reason="size",
        comment=None,
        status=status,
        payment_external_id=payment_external_id,
    )
    db_session.add(rr)
    await db_session.flush()
    return rr


class TestProcessRefund:
    """Тесты возврата денег с защитами (критичная логика)."""

    async def test_refund_approved_request(self, db_session):
        """Одобренная заявка: вызывается create_refund, статус → refunded."""
        order = await _make_order(db_session)
        rr = await _make_return(db_session, order, order.user_id, status="approved")

        # Мокаем create_refund — не зовём реальную YooKassa
        with patch.object(
            service.payment_service, "create_refund", return_value="succeeded"
        ) as mock_refund:
            await service.process_refund(db_session, rr)

        mock_refund.assert_called_once()
        assert rr.status == "refunded"

    async def test_refund_not_approved_raises(self, db_session):
        """Возврат по неодобренной (pending) заявке — ошибка, YooKassa не зовётся."""
        order = await _make_order(db_session)
        rr = await _make_return(db_session, order, order.user_id, status="pending")

        with patch.object(service.payment_service, "create_refund") as mock_refund:
            with pytest.raises(ReturnError, match="одобренной"):
                await service.process_refund(db_session, rr)

        mock_refund.assert_not_called()  # YooKassa НЕ вызывалась

    async def test_refund_already_refunded_raises(self, db_session):
        """Повторный возврат уже возвращённой заявки — блокируется."""
        order = await _make_order(db_session)
        rr = await _make_return(db_session, order, order.user_id, status="refunded")

        with patch.object(service.payment_service, "create_refund") as mock_refund:
            with pytest.raises(ReturnError, match="уже возвращены"):
                await service.process_refund(db_session, rr)

        mock_refund.assert_not_called()

    async def test_refund_no_payment_id_raises(self, db_session):
        """Заявка без id платежа — возврат невозможен."""
        order = await _make_order(db_session)
        rr = await _make_return(
            db_session,
            order,
            order.user_id,
            status="approved",
            payment_external_id=None,
        )

        with patch.object(service.payment_service, "create_refund") as mock_refund:
            with pytest.raises(ReturnError, match="платёж"):
                await service.process_refund(db_session, rr)

        mock_refund.assert_not_called()


class TestCreateReturnRequest:
    """Тесты создания заявки с защитами."""

    async def test_duplicate_request_blocked(self, db_session):
        """Нельзя создать вторую заявку при активной (pending)."""
        order = await _make_order(db_session)
        await _make_return(db_session, order, order.user_id, status="pending")

        with pytest.raises(ReturnError, match="уже есть"):
            await service.create_return_request(
                db_session,
                order_id=order.id,
                user_id=order.user_id,
                reason="size",
                comment=None,
            )

    async def test_request_after_reject_allowed(self, db_session):
        """После отклонения можно подать новую заявку."""
        order = await _make_order(db_session)
        await _make_return(db_session, order, order.user_id, status="rejected")

        # Не должно кинуть ошибку
        rr = await service.create_return_request(
            db_session,
            order_id=order.id,
            user_id=order.user_id,
            reason="size",
            comment=None,
        )
        assert rr.status == "pending"

    async def test_refunded_request_blocks_new(self, db_session):
        """Если деньги уже возвращены — новую заявку нельзя."""
        order = await _make_order(db_session)
        await _make_return(db_session, order, order.user_id, status="refunded")

        with pytest.raises(ReturnError, match="уже возвращены"):
            await service.create_return_request(
                db_session,
                order_id=order.id,
                user_id=order.user_id,
                reason="size",
                comment=None,
            )

    async def test_expired_window_blocks_non_defect(self, db_session):
        """Просроченный срок (>14 дней) блокирует обычный возврат."""
        old_date = datetime.now(timezone.utc) - timedelta(days=20)
        order = await _make_order(db_session, created_at=old_date)

        with pytest.raises(ReturnError, match="срок|Срок"):
            await service.create_return_request(
                db_session,
                order_id=order.id,
                user_id=order.user_id,
                reason="size",
                comment=None,
            )

    async def test_defect_ignores_window(self, db_session):
        """Брак можно вернуть даже после 14 дней."""
        old_date = datetime.now(timezone.utc) - timedelta(days=20)
        order = await _make_order(db_session, created_at=old_date)

        # Брак — срок не проверяется, заявка создаётся
        rr = await service.create_return_request(
            db_session,
            order_id=order.id,
            user_id=order.user_id,
            reason="defect",
            comment=None,
        )
        assert rr.status == "pending"


class TestMarkRefunded:
    """Тесты обработки webhook возврата."""

    async def test_mark_refunded_sets_status(self, db_session):
        """mark_refunded находит approved-заявку и ставит refunded."""
        from app.payments import service as payment_service

        order = await _make_order(db_session)
        rr = await _make_return(
            db_session,
            order,
            order.user_id,
            status="approved",
            payment_external_id="yoo_mark_1",
        )

        await payment_service.mark_refunded(db_session, "yoo_mark_1")
        await db_session.refresh(rr)
        assert rr.status == "refunded"
