from unittest.mock import MagicMock

import pytest

from app.users import rate_limit
from app.users.rate_limit import get_client_ip


class TestGetClientIp:
    """Тесты определения IP клиента."""

    def test_direct_connection(self):
        """Без прокси — берётся прямой адрес."""
        request = MagicMock()
        request.headers.get.return_value = None  # нет X-Forwarded-For
        request.client.host = "203.0.113.5"

        assert get_client_ip(request) == "203.0.113.5"

    def test_behind_proxy(self):
        """За прокси — берётся первый адрес из X-Forwarded-For."""
        request = MagicMock()
        request.headers.get.return_value = "198.51.100.10"

        assert get_client_ip(request) == "198.51.100.10"

    def test_proxy_chain(self):
        """Цепочка прокси — берём ПОСЛЕДНИЙ адрес (его проставил наш nginx);
        первый элемент клиент может подделать."""
        request = MagicMock()
        request.headers.get.return_value = "198.51.100.10, 10.0.0.1, 10.0.0.2"

        assert get_client_ip(request) == "10.0.0.2"

    def test_spoofed_xff_ignored(self):
        """Клиент подсунул фейковый первый адрес — берём реальный, что добавил nginx."""
        request = MagicMock()
        request.headers.get.return_value = "1.1.1.1, 203.0.113.5"

        assert get_client_ip(request) == "203.0.113.5"

    def test_no_client(self):
        """Нет ни заголовка, ни client — возвращаем unknown."""
        request = MagicMock()
        request.headers.get.return_value = None
        request.client = None

        assert get_client_ip(request) == "unknown"


class TestRegistrationLimit:
    """Анти-спам ограничение на регистрацию по IP."""

    @pytest.mark.asyncio
    async def test_blocks_after_limit(self, fake_redis):
        ip = "203.0.113.9"
        # До лимита — не заблокирован
        for _ in range(rate_limit.REGISTER_MAX):
            assert not await rate_limit.is_blocked(
                fake_redis, ip, action="register", max_attempts=rate_limit.REGISTER_MAX
            )
            await rate_limit.register_attempt(
                fake_redis, ip, action="register", window_seconds=3600
            )
        # На лимите — заблокирован
        assert await rate_limit.is_blocked(
            fake_redis, ip, action="register", max_attempts=rate_limit.REGISTER_MAX
        )

    @pytest.mark.asyncio
    async def test_separate_namespace_from_login(self, fake_redis):
        """Счётчик регистрации не пересекается с логином."""
        ip = "203.0.113.10"
        await rate_limit.register_attempt(
            fake_redis, ip, action="register", window_seconds=3600
        )
        # Логин-счётчик этого IP всё ещё пуст
        assert not await rate_limit.is_blocked(fake_redis, ip)
