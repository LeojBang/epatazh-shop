"""
Тесты для app/core/config.py — валидация продакшен-конфигурации.

_validate_production() должна:
  - пропускать local/staging без проверок
  - блокировать старт при слабом SECRET_KEY на проде
  - блокировать при DEBUG=True на проде
  - блокировать при заглушках ЮKassa на проде
  - пропускать при корректных значениях
"""

import pytest

from app.core.config import Settings, _validate_production


def _make_settings(**overrides) -> Settings:
    """Создаёт Settings с валидными продовыми значениями, перекрывая указанные поля."""
    defaults = dict(
        ENVIRONMENT="production",
        DEBUG=False,
        DATABASE_URL="postgresql+asyncpg://user:pass@db:5432/shop",
        SECRET_KEY="a" * 48,  # достаточно длинный, не из списка заглушек
        YOOKASSA_SHOP_ID="123456",
        YOOKASSA_SECRET_KEY="live_MTIzNDU2Onl",
        CDEK_ACCOUNT="real_account",
        CDEK_SECURE_PASSWORD="real_password",
        CDEK_API_URL="https://api.cdek.ru",
    )
    defaults.update(overrides)
    # Обходим загрузку .env — передаём значения напрямую
    return Settings.model_construct(**defaults)


class TestValidateProductionSkipsNonProd:
    """На не-продовых окружениях валидация не запускается."""

    def test_local_skips_validation(self):
        """ENVIRONMENT=local — даже слабый ключ не вызывает ошибки."""
        s = _make_settings(ENVIRONMENT="local", SECRET_KEY="weak", DEBUG=True)
        # Не должно бросить исключение
        _validate_production(s)

    def test_staging_skips_validation(self):
        """ENVIRONMENT=staging — тоже пропускается."""
        s = _make_settings(ENVIRONMENT="staging", SECRET_KEY="weak", DEBUG=True)
        _validate_production(s)


class TestValidateProductionSecretKey:
    """Проверки SECRET_KEY на проде."""

    def test_short_secret_key_raises(self):
        """SECRET_KEY короче 32 символов → RuntimeError."""
        s = _make_settings(SECRET_KEY="tooshort")
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _validate_production(s)

    def test_empty_secret_key_raises(self):
        """Пустой SECRET_KEY → RuntimeError."""
        s = _make_settings(SECRET_KEY="")
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _validate_production(s)

    @pytest.mark.parametrize(
        "insecure",
        [
            "your-secret-key-here",
            "change-me",
            "secret",
        ],
    )
    def test_insecure_placeholder_raises(self, insecure):
        """Известные заглушки → RuntimeError, даже если длина ≥ 32."""
        s = _make_settings(SECRET_KEY=insecure)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _validate_production(s)

    def test_valid_secret_key_passes(self):
        """Длинный случайный ключ → ОК."""
        s = _make_settings(SECRET_KEY="x" * 48)
        _validate_production(s)  # не должно бросать


class TestValidateProductionDebug:
    """Проверки флага DEBUG на проде."""

    def test_debug_true_raises(self):
        """DEBUG=True на production → RuntimeError."""
        s = _make_settings(DEBUG=True)
        with pytest.raises(RuntimeError, match="DEBUG"):
            _validate_production(s)

    def test_debug_false_passes(self):
        """DEBUG=False → ОК."""
        s = _make_settings(DEBUG=False)
        _validate_production(s)


class TestValidateProductionYookassa:
    """Проверки ключей ЮKassa на проде."""

    def test_placeholder_shop_id_raises(self):
        """your-shop-id в YOOKASSA_SHOP_ID → RuntimeError."""
        s = _make_settings(YOOKASSA_SHOP_ID="your-shop-id")
        with pytest.raises(RuntimeError, match="[Yy]oo[Kk]assa|YOOKASSA"):
            _validate_production(s)

    def test_placeholder_secret_key_raises(self):
        """your-secret-key в YOOKASSA_SECRET_KEY → RuntimeError."""
        s = _make_settings(YOOKASSA_SECRET_KEY="your-secret-key-here")
        with pytest.raises(RuntimeError, match="[Yy]oo[Kk]assa|YOOKASSA"):
            _validate_production(s)

    def test_real_yookassa_keys_pass(self):
        """Реальные ключи (без заглушек) → ОК."""
        s = _make_settings(
            YOOKASSA_SHOP_ID="987654",
            YOOKASSA_SECRET_KEY="live_MTIzNDU2Onl",
        )
        _validate_production(s)


class TestValidateProductionMultipleErrors:
    """При нескольких проблемах одновременно — все попадают в одно исключение."""

    def test_multiple_problems_in_one_error(self):
        """Слабый ключ + DEBUG=True — оба упоминаются в тексте ошибки."""
        s = _make_settings(SECRET_KEY="weak", DEBUG=True)
        with pytest.raises(RuntimeError) as exc_info:
            _validate_production(s)
        msg = str(exc_info.value)
        assert "SECRET_KEY" in msg
        assert "DEBUG" in msg


class TestValidateProductionFullyValid:
    """Полностью корректный продовый конфиг — стартует без ошибок."""

    def test_all_valid_passes(self):
        """Все поля в порядке → никаких исключений."""
        import secrets

        s = _make_settings(
            SECRET_KEY=secrets.token_urlsafe(48),
            DEBUG=False,
            YOOKASSA_SHOP_ID="123456",
            YOOKASSA_SECRET_KEY="live_real_key_here",
        )
        _validate_production(s)
