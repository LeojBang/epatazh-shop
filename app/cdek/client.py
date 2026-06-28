"""
Клиент для работы с API СДЭК v2.

Документация: https://api-docs.cdek.ru/

Использование тестовой/боевой среды переключается в настройках:
  CDEK_API_URL, CDEK_ACCOUNT, CDEK_SECURE_PASSWORD.

Токен авторизации кешируется в памяти и обновляется автоматически,
когда истекает срок его действия.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class CdekError(Exception):
    """Ошибка при обращении к API СДЭК."""


class CdekClient:
    def __init__(self) -> None:
        self._base_url = settings.CDEK_API_URL.rstrip("/")
        self._account = settings.CDEK_ACCOUNT
        self._password = settings.CDEK_SECURE_PASSWORD
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ---------- авторизация ----------

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        """Возвращает валидный токен, при необходимости запрашивая новый."""
        # 60 секунд запаса, чтобы не использовать токен на грани истечения
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        resp = await client.post(
            f"{self._base_url}/v2/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._account,
                "client_secret": self._password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            logger.error(
                "СДЭК авторизация не удалась: %s %s", resp.status_code, resp.text
            )
            raise CdekError("Не удалось авторизоваться в СДЭК")

        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Выполняет авторизованный запрос к API СДЭК."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            token = await self._get_token(client)
            resp = await client.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=json,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code >= 400:
                logger.error(
                    "СДЭК %s %s -> %s %s", method, path, resp.status_code, resp.text
                )
                raise CdekError(f"Ошибка СДЭК: {resp.status_code}")
            if resp.content:
                return resp.json()
            return None

    # ---------- города (для подсказок) ----------

    async def find_cities(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Поиск городов по части названия — для автоподсказок при оформлении.
        Возвращает список словарей с кодом и названием города.
        """
        if not query or len(query) < 2:
            return []
        data = await self._request(
            "GET",
            "/v2/location/cities",
            params={"city": query, "country_codes": "RU", "size": limit},
        )
        result = []
        for c in data or []:
            result.append(
                {
                    "code": c.get("code"),
                    "city": c.get("city"),
                    "region": c.get("region"),
                    "full_name": _format_city(c),
                }
            )
        return result

    async def get_city_code(
        self, name: str, postal_code: str | None = None
    ) -> int | None:
        """Возвращает код города СДЭК по названию (или индексу)."""
        params: dict[str, Any] = {"country_codes": "RU", "size": 1}
        if postal_code:
            params["postal_code"] = postal_code
        else:
            params["city"] = name
        data = await self._request("GET", "/v2/location/cities", params=params)
        if data:
            return data[0].get("code")
        return None

    # ---------- пункты выдачи ----------

    async def get_delivery_points(self, city_code: int) -> list[dict[str, Any]]:
        """Список пунктов выдачи (ПВЗ) в указанном городе."""
        data = await self._request(
            "GET",
            "/v2/deliverypoints",
            params={"city_code": city_code, "type": "PVZ", "country_code": "RU"},
        )
        result = []
        for p in data or []:
            loc = p.get("location", {})
            result.append(
                {
                    "code": p.get("code"),
                    "name": p.get("name"),
                    "address": loc.get("address_full") or loc.get("address"),
                    "latitude": loc.get("latitude"),
                    "longitude": loc.get("longitude"),
                    "work_time": p.get("work_time"),
                    "phone": _first_phone(p.get("phones")),
                }
            )
        return result

    # ---------- заказы ----------

    async def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Регистрирует заказ в СДЭК. Возвращает ответ с uuid заказа."""
        return await self._request("POST", "/v2/orders", json=payload)

    async def get_order(self, cdek_uuid: str) -> dict[str, Any]:
        """Информация по заказу (включая статусы) для отслеживания."""
        return await self._request("GET", f"/v2/orders/{cdek_uuid}")

    async def calculate_tariff(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Расчёт стоимости и срока доставки по коду тарифа."""
        return await self._request("POST", "/v2/calculator/tariff", json=payload)


def _format_city(c: dict[str, Any]) -> str:
    parts = [c.get("city")]
    if c.get("region") and c.get("region") != c.get("city"):
        parts.append(c.get("region"))
    return ", ".join(p for p in parts if p)


def _first_phone(phones: Any) -> str | None:
    if isinstance(phones, list) and phones:
        return phones[0].get("number")
    return None


# единый экземпляр клиента на всё приложение
cdek_client = CdekClient()
