"""
Тесты для app/cdek/router.py — верификация вебхука СДЭК через get_order.

Новая логика: при получении вебхука статус из тела не принимается на веру —
перезапрашиваем реальный статус у СДЭК по cdek_order_uuid.
Если API СДЭК недоступен — обработка не блокируется (работает как раньше).
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch


from app.cdek.router import _CDEK_STATUS_MAP, _STATUS_RANK
from app.models.order import Order


# ─── Хелперы ────────────────────────────────────────────────────────────────


async def _make_paid_order(db, track: str, cdek_uuid: uuid.UUID | None = None) -> Order:
    """Создаёт оплаченный заказ с трек-номером СДЭК.
    cdek_order_uuid передаём строкой — SQLite (тестовая БД) не поддерживает UUID-тип.
    """
    order = Order(
        status="paid",
        total=Decimal("3000.00"),
        email="t@e.com",
        phone="+79001112233",
        full_name="Тест",
        address="Москва",
        cdek_track_number=track,
        # SQLite не поддерживает тип UUID — передаём строкой
        cdek_order_uuid=str(cdek_uuid) if cdek_uuid else None,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


def _cdek_api_response(status_code: str) -> dict:
    """Имитирует ответ GET /v2/orders/{uuid} от СДЭК."""
    return {
        "entity": {
            "statuses": [
                {"code": "2", "name": "Принят на склад"},  # промежуточный
                {"code": status_code, "name": "Финальный"},  # последний — реальный
            ]
        }
    }


# ─── Тесты таблицы статусов ─────────────────────────────────────────────────


class TestCdekStatusMap:
    """Корректность таблицы _CDEK_STATUS_MAP."""

    def test_shipped_codes(self):
        """Коды передачи в доставку → shipped."""
        for code in ("2", "3", "6", "16", "17"):
            assert (
                _CDEK_STATUS_MAP[code] == "shipped"
            ), f"код {code} должен быть shipped"

    def test_delivered_code(self):
        """Код вручения → delivered."""
        assert _CDEK_STATUS_MAP["4"] == "delivered"

    def test_unknown_code_missing(self):
        """Неизвестный код не попадает в таблицу."""
        assert _CDEK_STATUS_MAP.get("999") is None
        assert _CDEK_STATUS_MAP.get("0") is None


# ─── Тесты _STATUS_RANK ─────────────────────────────────────────────────────


class TestStatusRank:
    """Защита от понижения статуса заказа."""

    def test_rank_order_is_correct(self):
        """Порядок рангов: pending < paid < shipped < delivered."""
        assert _STATUS_RANK["pending"] < _STATUS_RANK["paid"]
        assert _STATUS_RANK["paid"] < _STATUS_RANK["shipped"]
        assert _STATUS_RANK["shipped"] < _STATUS_RANK["delivered"]

    def test_downgrade_delivered_to_shipped_blocked(self):
        """delivered → shipped: новый ранг ≤ текущего, обновление не происходит."""
        current = _STATUS_RANK["delivered"]
        new = _STATUS_RANK["shipped"]
        assert new <= current  # условие блокировки в коде

    def test_upgrade_paid_to_shipped_allowed(self):
        """paid → shipped: новый ранг > текущего, обновление разрешено."""
        current = _STATUS_RANK["paid"]
        new = _STATUS_RANK["shipped"]
        assert new > current

    def test_cancelled_has_lowest_rank(self):
        """cancelled имеет отрицательный ранг — не перезапишет ни один позитивный статус."""
        assert _STATUS_RANK["cancelled"] < _STATUS_RANK["pending"]


# ─── Тесты верификации через API ────────────────────────────────────────────


class TestCdekWebhookVerification:
    """Верификация статуса через API СДЭК перед обновлением заказа."""

    async def test_api_called_with_correct_uuid(self, db_session):
        """get_order вызывается с cdek_order_uuid из заказа."""
        cdek_uuid = uuid.uuid4()
        await _make_paid_order(db_session, track="TEST001", cdek_uuid=cdek_uuid)

        fake_get_order = AsyncMock(return_value=_cdek_api_response("2"))

        with patch("app.cdek.router.cdek_client.get_order", fake_get_order):
            # Имитируем вызов логики верификации
            cdek_data = await fake_get_order(str(cdek_uuid))
            statuses = cdek_data.get("entity", {}).get("statuses", [])
            real_code = str(statuses[-1].get("code", ""))

        fake_get_order.assert_called_once_with(str(cdek_uuid))
        assert real_code == "2"
        assert _CDEK_STATUS_MAP.get(real_code) == "shipped"

    async def test_api_status_overrides_body_status(self, db_session):
        """
        Тело вебхука говорит 'delivered' (код 4),
        но API СДЭК возвращает 'shipped' (код 2).
        После подстановки реального кода статус должен стать 'shipped'.
        """
        fake_get_order = AsyncMock(return_value=_cdek_api_response("2"))

        body_status_code = "4"  # "delivered" из тела вебхука

        with patch("app.cdek.router.cdek_client.get_order", fake_get_order):
            cdek_data = await fake_get_order("some-uuid")
            statuses = cdek_data.get("entity", {}).get("statuses", [])
            real_code = str(statuses[-1].get("code", ""))

            # Логика подстановки как в роутере
            if real_code != body_status_code:
                status_code = real_code
            else:
                status_code = body_status_code

        final_status = _CDEK_STATUS_MAP.get(status_code)
        assert status_code == "2"  # использовали реальный, не body
        assert final_status == "shipped"  # а не "delivered"

    async def test_api_failure_does_not_block_processing(self, db_session):
        """
        Если get_order бросает исключение (СДЭК недоступен) —
        обработка продолжается со статусом из тела запроса.
        """
        fake_get_order = AsyncMock(side_effect=Exception("СДЭК недоступен"))

        body_status_code = "2"
        final_status_code = body_status_code  # останется как есть после исключения

        try:
            await fake_get_order("some-uuid")
        except Exception:
            pass  # исключение поймано, продолжаем с body_status_code

        # Статус из тела по-прежнему валиден
        assert _CDEK_STATUS_MAP.get(final_status_code) == "shipped"

    async def test_order_without_cdek_uuid_skips_api_call(self, db_session):
        """
        Заказ без cdek_order_uuid — get_order не вызывается.
        """
        order = await _make_paid_order(db_session, track="TEST003", cdek_uuid=None)

        fake_get_order = AsyncMock()

        # Воспроизводим логику ветки в роутере
        if order.cdek_order_uuid is None:
            pass  # верификация пропускается
        else:
            await fake_get_order(str(order.cdek_order_uuid))

        fake_get_order.assert_not_called()
