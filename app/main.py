from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.catalog.router import router as catalog_router
from app.users.router import router as users_router
from app.web.router import router as web_router

app = FastAPI(title=settings.PROJECT_NAME, debug=settings.DEBUG)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(web_router)
app.include_router(users_router)
app.include_router(catalog_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
