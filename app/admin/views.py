from sqladmin import BaseView, expose
from starlette.requests import Request

from app.core.database import AsyncSessionLocal
from app.analytics import service as analytics_service
from wtforms import SelectField

from sqladmin import ModelView

from app.models.order import Order, OrderItem
from app.models.user import User
from app.models.catalog import Category, Product, ProductVariant, ProductImage
from app.models.review import Review
from app.models.page import InfoPage

from datetime import timezone, timedelta


def _msk(value):
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")


class UserAdmin(ModelView, model=User):
    name = "Пользователь"
    name_plural = "Пользователи"
    category = "Сервис"
    column_list = [
        User.email,
        User.full_name,
        User.is_active,
        User.is_superuser,
        User.created_at,
    ]
    column_searchable_list = [User.email]
    column_sortable_list = [User.created_at]
    form_excluded_columns = [User.hashed_password, User.created_at, User.updated_at]
    can_delete = False


class CategoryAdmin(ModelView, model=Category):
    name = "Категория"
    name_plural = "Категории"
    category = "Каталог"
    column_list = [Category.name, Category.slug]
    form_excluded_columns = [
        Category.products,
        Category.created_at,
        Category.updated_at,
    ]


class ProductAdmin(ModelView, model=Product):
    name = "Товар"
    name_plural = "Товары"
    category = "Каталог"
    column_list = [
        Product.name,
        Product.price,
        Product.badge,
        Product.is_active,
        Product.category,
    ]
    column_searchable_list = [Product.name]
    column_sortable_list = [Product.price]
    form_excluded_columns = [Product.created_at, Product.updated_at]


class OrderAdmin(ModelView, model=Order):
    category = "Продажи"
    name = "Заказ"
    name_plural = "Заказы"
    column_list = [
        Order.created_at, Order.full_name, Order.email,
        Order.phone, Order.total, Order.status,
    ]
    column_details_list = [
        Order.created_at, Order.full_name, Order.email, Order.phone,
        Order.address, Order.total, Order.status,
    ]

    column_searchable_list = [Order.email, Order.full_name, Order.phone]
    column_sortable_list = [Order.created_at, Order.total, Order.status]
    column_default_sort = [("created_at", True)]  # новые сверху
    can_create = False
    page_size = 50
    column_formatters_detail = {
        Order.status: lambda m, a: {
            "new": "Новый", "pending": "Ожидает оплаты", "paid": "Оплачен",
            "cancelled": "Отменён", "shipped": "Отправлен",
        }.get(m.status, m.status),
        Order.created_at: lambda m, a: _msk(m.created_at),
    }
    form_overrides = {"status": SelectField}
    form_args = {
        "status": {
            "choices": [
                ("new", "Новый"),
                ("pending", "Ожидает оплаты"),
                ("paid", "Оплачен"),
                ("shipped", "Отправлен"),
                ("cancelled", "Отменён"),
            ]
        }
    }

    async def on_model_change(self, data, model, is_created, request):
        # Возврат товара на склад при ручной отмене заказа.
        # model.status здесь — ещё СТАРЫЙ статус (до применения изменений),
        # data["status"] — новый, который выбрали в форме.
        new_status = data.get("status")
        old_status = model.status

        if new_status == "cancelled" and old_status != "cancelled":
            from sqlalchemy import select, text
            from app.models.order import Order
            from sqlalchemy.orm import selectinload

            # Берём позиции заказа и возвращаем остатки
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Order)
                    .where(Order.id == model.id)
                    .options(selectinload(Order.items))
                )
                order = result.scalar_one_or_none()
                if order:
                    for item in order.items:
                        if item.variant_id:
                            await db.execute(
                                text(
                                    "UPDATE product_variants SET stock = stock + :qty WHERE id = :id"
                                ),
                                {"qty": item.quantity, "id": item.variant_id},
                            )
                    await db.commit()


class OrderItemAdmin(ModelView, model=OrderItem):
    name = "Позиция заказа"
    name_plural = "Позиции заказов"
    category = "Продажи"
    column_list = [OrderItem.product_name, OrderItem.price, OrderItem.quantity]
    can_create = False
    can_edit = False


class ProductVariantAdmin(ModelView, model=ProductVariant):
    name = "Вариант товара"
    name_plural = "Размеры товаров"
    category = "Каталог"
    column_list = [ProductVariant.product, ProductVariant.size, ProductVariant.stock]
    column_formatters = {
        ProductVariant.product: lambda m, a: m.product.name if m.product else ""
    }
    form_excluded_columns = [ProductVariant.created_at, ProductVariant.updated_at]
    # Сортировка и поиск
    column_sortable_list = [ProductVariant.size, ProductVariant.stock]
    column_searchable_list = [ProductVariant.size]
    # Сразу показывать побольше записей и сортировать по товару
    page_size = 100
    column_default_sort = [("product_id", True)]


class ProductImageAdmin(ModelView, model=ProductImage):
    name = "Фото товара"
    name_plural = "Фото товаров"
    category = "Каталог"
    column_list = [ProductImage.product, ProductImage.path, ProductImage.position]
    column_formatters = {
        ProductImage.product: lambda m, a: m.product.name if m.product else ""
    }
    # path заполнится автоматически из загруженного файла — скрываем из формы
    form_excluded_columns = [
        ProductImage.path,
        ProductImage.created_at,
        ProductImage.updated_at,
    ]

    async def scaffold_form(self, rules=None):
        from wtforms import FileField

        form_class = await super().scaffold_form(rules)
        # Добавляем поле загрузки файла в форму
        form_class.upload = FileField("Файл изображения")
        return form_class

    async def on_model_change(self, data, model, is_created, request):
        from app.admin.uploads import save_upload

        upload = data.get("upload")
        if upload:
            filename = await save_upload(upload)
            if filename:
                model.path = filename
        # убираем upload из data, чтобы sqladmin не пытался записать его в модель
        data.pop("upload", None)


class ReviewAdmin(ModelView, model=Review):
    name = "Отзыв"
    name_plural = "Отзывы"
    category = "Контент"
    column_list = [Review.product, Review.rating, Review.is_approved, Review.created_at]
    column_sortable_list = [Review.created_at, Review.is_approved]
    form_excluded_columns = [Review.created_at, Review.updated_at]
    column_formatters = {
        Review.product: lambda m, a: m.product.name if m.product else ""
    }


class DashboardView(BaseView):
    name = "Аналитика"
    category = "Сервис"

    @expose("/dashboard", methods=["GET"])
    async def dashboard(self, request: Request):
        from fastapi.templating import Jinja2Templates

        templates = Jinja2Templates(directory="app/templates")
        days = int(request.query_params.get("days", 30))

        async with AsyncSessionLocal() as db:
            summary = await analytics_service.get_summary(db, days)
            top_products = await analytics_service.get_top_products(db, days)
            revenue_by_day = await analytics_service.get_revenue_by_day(db, days)

        return templates.TemplateResponse(
            request,
            "admin/dashboard.html",
            {
                "summary": summary,
                "top_products": top_products,
                "revenue_by_day": revenue_by_day,
            },
        )


class InfoPageAdmin(ModelView, model=InfoPage):
    name = "Страница"
    name_plural = "Страницы"
    category = "Контент"
    column_list = [
        InfoPage.title,
        InfoPage.slug,
        InfoPage.footer_group,
        InfoPage.position,
        InfoPage.is_published,
    ]
    column_sortable_list = [InfoPage.footer_group, InfoPage.position]
    form_excluded_columns = [InfoPage.created_at, InfoPage.updated_at]


class StockView(BaseView):
    name = "Склад"
    category = "Сервис"

    @expose("/stock", methods=["GET", "POST"])
    async def stock(self, request: Request):
        from fastapi.templating import Jinja2Templates
        from sqlalchemy import select, text
        from sqlalchemy.orm import selectinload
        from app.models.catalog import Product

        templates = Jinja2Templates(directory="app/templates")
        saved = False

        async with AsyncSessionLocal() as db:
            # Сохранение: пришла форма с остатками
            if request.method == "POST":
                form = await request.form()
                for key, value in form.items():
                    # поля вида stock_<variant_id>
                    if key.startswith("stock_"):
                        variant_id = key[len("stock_"):]
                        try:
                            new_stock = int(value)
                            if new_stock < 0:
                                new_stock = 0
                            await db.execute(
                                text(
                                    "UPDATE product_variants SET stock = :s WHERE id = :id"
                                ),
                                {"s": new_stock, "id": variant_id},
                            )
                        except (ValueError, TypeError):
                            continue
                await db.commit()
                saved = True

            # Загрузка всех товаров с вариантами
            result = await db.execute(
                select(Product)
                .options(selectinload(Product.variants), selectinload(Product.category))
                .order_by(Product.name)
            )
            products = list(result.scalars().all())

        return templates.TemplateResponse(
            request, "admin/stock.html", {"products": products, "saved": saved}
        )
