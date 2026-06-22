from unittest.mock import MagicMock

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
        """Цепочка прокси — берётся первый (настоящий клиент)."""
        request = MagicMock()
        request.headers.get.return_value = "198.51.100.10, 10.0.0.1, 10.0.0.2"

        assert get_client_ip(request) == "198.51.100.10"

    def test_no_client(self):
        """Нет ни заголовка, ни client — возвращаем unknown."""
        request = MagicMock()
        request.headers.get.return_value = None
        request.client = None

        assert get_client_ip(request) == "unknown"
