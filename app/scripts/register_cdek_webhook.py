"""
Регистрация вебхука в СДЭК — запускается ОДИН РАЗ после деплоя.

СДЭК будет слать уведомления об изменении статусов заказов на
наш URL, а мы будем автоматически обновлять статусы в магазине.

Запуск (на сервере):
    docker compose -f docker-compose.prod.yml exec app \
        python -m app.scripts.register_cdek_webhook

Проверить текущие подписки:
    python -m app.scripts.register_cdek_webhook --list

Удалить подписку (если нужно откатить):
    python -m app.scripts.register_cdek_webhook --delete <uuid>
"""

import asyncio
import sys

import httpx

from app.core.config import settings


async def get_token(client: httpx.AsyncClient) -> str:
    r = await client.post(
        f"{settings.CDEK_API_URL}/v2/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": settings.CDEK_ACCOUNT,
            "client_secret": settings.CDEK_SECURE_PASSWORD,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    r.raise_for_status()
    return r.json()["access_token"]


async def list_webhooks(client: httpx.AsyncClient, token: str) -> list[dict]:
    r = await client.get(
        f"{settings.CDEK_API_URL}/v2/webhooks",
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    data = r.json()
    # ответ может быть списком или объектом с entity
    if isinstance(data, list):
        return data
    return data.get("entity", []) if data else []


async def register(client: httpx.AsyncClient, token: str, webhook_url: str) -> str:
    r = await client.post(
        f"{settings.CDEK_API_URL}/v2/webhooks",
        json={"type": "ORDER_STATUS", "url": webhook_url},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    r.raise_for_status()
    data = r.json()
    return data.get("entity", {}).get("uuid", "")


async def delete_webhook(client: httpx.AsyncClient, token: str, uuid: str) -> None:
    r = await client.delete(
        f"{settings.CDEK_API_URL}/v2/webhooks/{uuid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()


async def main() -> None:
    webhook_url = "https://shop.epatajextra.ru/api/cdek/webhook"

    print("=" * 50)
    print("Регистрация вебхука СДЭК")
    print("=" * 50)
    print(f"  API URL      : {settings.CDEK_API_URL}")
    print(f"  Webhook URL  : {webhook_url}")
    print(f"  AUTO_STATUS  : {settings.CDEK_AUTO_STATUS}")
    print("-" * 50)

    async with httpx.AsyncClient(timeout=20) as client:
        token = await get_token(client)
        print("✓ Токен получен")

        if "--list" in sys.argv:
            webhooks = await list_webhooks(client, token)
            print(f"\nТекущие подписки ({len(webhooks)}):")
            for w in webhooks:
                e = w.get("entity", w)
                print(
                    f"  UUID: {e.get('uuid')}  type: {e.get('type')}  url: {e.get('url')}"
                )
            return

        if "--delete" in sys.argv:
            idx = sys.argv.index("--delete")
            uuid = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
            if not uuid:
                print("✗ Укажите UUID: --delete <uuid>")
                return
            await delete_webhook(client, token, uuid)
            print(f"✓ Подписка {uuid} удалена")
            return

        # Проверяем, нет ли уже подписки на наш URL
        existing = await list_webhooks(client, token)
        for w in existing:
            e = w.get("entity", w)
            if e.get("url") == webhook_url and e.get("type") == "ORDER_STATUS":
                print(f"✓ Подписка уже существует: {e.get('uuid')}")
                print("  Ничего не делаем — дублировать не нужно.")
                return

        # Регистрируем
        uuid = await register(client, token, webhook_url)
        if uuid:
            print("✓ Вебхук зарегистрирован!")
            print(f"  UUID: {uuid}")
            print(f"  URL:  {webhook_url}")
            print("\nТеперь СДЭК будет слать уведомления о статусах заказов.")
            print("Чтобы проверить: --list")
        else:
            print("✗ Не удалось получить UUID — проверьте ответ СДЭК вручную.")


if __name__ == "__main__":
    asyncio.run(main())
