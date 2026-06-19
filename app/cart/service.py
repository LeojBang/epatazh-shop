import json
import uuid

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.service import get_product_by_slug

CART_TTL = 60 * 60 * 24 * 7  # 7 дней


def _cart_key(user_id: str) -> str:
    return f"cart:{user_id}"


async def get_cart(r: redis.Redis, user_id: str) -> dict[str, int]:
    data = await r.get(_cart_key(user_id))
    return json.loads(data) if data else {}


async def add_to_cart(
    r: redis.Redis,
    db: AsyncSession,
    user_id: str,
    product_slug: str,
    quantity: int = 1,
) -> dict:
    product = await get_product_by_slug(db, product_slug)
    if not product:
        return {"ok": False, "error": "Товар не найден"}
    if product.stock == 0:
        return {"ok": False, "error": "Товара нет в наличии"}

    cart = await get_cart(r, user_id)
    current_qty = cart.get(product_slug, 0)
    cart[product_slug] = current_qty + quantity

    key = _cart_key(user_id)
    await r.set(key, json.dumps(cart), ex=CART_TTL)
    return {"ok": True, "cart": cart}


async def remove_from_cart(r: redis.Redis, user_id: str, product_slug: str) -> None:
    cart = await get_cart(r, user_id)
    cart.pop(product_slug, None)
    key = _cart_key(user_id)
    await r.set(key, json.dumps(cart), ex=CART_TTL)


async def update_quantity(
    r: redis.Redis, user_id: str, product_slug: str, quantity: int
) -> None:
    cart = await get_cart(r, user_id)
    if quantity <= 0:
        cart.pop(product_slug, None)
    else:
        cart[product_slug] = quantity
    key = _cart_key(user_id)
    await r.set(key, json.dumps(cart), ex=CART_TTL)


async def clear_cart(r: redis.Redis, user_id: str) -> None:
    await r.delete(_cart_key(user_id))


async def get_cart_with_products(
    r: redis.Redis, db: AsyncSession, user_id: str
) -> tuple[list[dict], float]:
    """Возвращает список позиций с данными товара и итоговую сумму."""
    cart = await get_cart(r, user_id)
    items = []
    total = 0.0

    for slug, qty in cart.items():
        product = await get_product_by_slug(db, slug)
        if product:
            subtotal = float(product.price) * qty
            total += subtotal
            items.append({"product": product, "quantity": qty, "subtotal": subtotal})

    return items, total
