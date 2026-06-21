from fastapi.templating import Jinja2Templates

from app.web.filters import order_status_ru

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["order_status_ru"] = order_status_ru
