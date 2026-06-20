import json

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.service import get_variant

CART_TTL = 60 * 60 * 24 * 7  # 7 дней


def _cart_key(user_id: str) -> str:
    return f"cart:{user_id}"


async def get_cart(r: redis.Redis, user_id: str) -> dict[str, int]:
    """Возвращает {variant_id: quantity}."""
    data = await r.get(_cart_key(user_id))
    return json.loads(data) if data else {}


async def add_to_cart(
    r: redis.Redis,
    db: AsyncSession,
    user_id: str,
    variant_id: str,
    quantity: int = 1,
) -> dict:
    variant = await get_variant(db, variant_id)
    if not variant:
        return {"ok": False, "error": "Вариант товара не найден"}
    if variant.stock == 0:
        return {"ok": False, "error": "Этого размера нет в наличии"}

    cart = await get_cart(r, user_id)
    current_qty = cart.get(variant_id, 0)
    cart[variant_id] = current_qty + quantity

    await r.set(_cart_key(user_id), json.dumps(cart), ex=CART_TTL)
    return {"ok": True, "cart": cart}


async def remove_from_cart(r: redis.Redis, user_id: str, variant_id: str) -> None:
    cart = await get_cart(r, user_id)
    cart.pop(variant_id, None)
    await r.set(_cart_key(user_id), json.dumps(cart), ex=CART_TTL)


async def update_quantity(
    r: redis.Redis, user_id: str, variant_id: str, quantity: int
) -> None:
    cart = await get_cart(r, user_id)
    if quantity <= 0:
        cart.pop(variant_id, None)
    else:
        cart[variant_id] = quantity
    await r.set(_cart_key(user_id), json.dumps(cart), ex=CART_TTL)


async def clear_cart(r: redis.Redis, user_id: str) -> None:
    await r.delete(_cart_key(user_id))


async def get_cart_with_products(
    r: redis.Redis, db: AsyncSession, user_id: str
) -> tuple[list[dict], float]:
    """Возвращает список позиций с данными варианта/товара и итоговую сумму."""
    cart = await get_cart(r, user_id)
    items = []
    total = 0.0

    for variant_id, qty in cart.items():
        variant = await get_variant(db, variant_id)
        if variant and variant.product:
            subtotal = float(variant.product.price) * qty
            total += subtotal
            items.append({
                "variant": variant,
                "product": variant.product,
                "quantity": qty,
                "subtotal": subtotal,
            })

    return items, total