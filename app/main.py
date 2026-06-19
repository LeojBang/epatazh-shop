from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin

from app.admin.auth import AdminAuth
from app.admin.views import (
    CategoryAdmin,
    OrderAdmin,
    OrderItemAdmin,
    ProductAdmin,
    UserAdmin,
)
from app.cart.router import router as cart_router
from app.catalog.router import router as catalog_router
from app.core.config import settings
from app.core.database import engine
from app.orders.router import router as orders_router
from app.users.router import router as users_router
from app.web.router import router as web_router

app = FastAPI(title=settings.PROJECT_NAME, debug=settings.DEBUG)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(web_router)
app.include_router(users_router)
app.include_router(catalog_router)
app.include_router(cart_router)
app.include_router(orders_router)

# --- Админка ---
admin = Admin(app, engine, authentication_backend=AdminAuth(secret_key=settings.SECRET_KEY))
admin.add_view(UserAdmin)
admin.add_view(CategoryAdmin)
admin.add_view(ProductAdmin)
admin.add_view(OrderAdmin)
admin.add_view(OrderItemAdmin)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}