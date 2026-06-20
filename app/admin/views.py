from sqladmin import BaseView, expose
from starlette.requests import Request

from app.core.database import AsyncSessionLocal
from app.analytics import service as analytics_service

from sqladmin import ModelView

from app.models.order import Order, OrderItem
from app.models.user import User
from app.models.catalog import Category, Product, ProductVariant, ProductImage
from app.models.review import Review


class UserAdmin(ModelView, model=User):
    name = "Пользователь"
    name_plural = "Пользователи"
    column_list = [User.email, User.full_name, User.is_active, User.is_superuser, User.created_at]
    column_searchable_list = [User.email]
    column_sortable_list = [User.created_at]
    form_excluded_columns = [User.hashed_password, User.created_at, User.updated_at]
    can_delete = False


class CategoryAdmin(ModelView, model=Category):
    name = "Категория"
    name_plural = "Категории"
    column_list = [Category.name, Category.slug]
    form_excluded_columns = [Category.products, Category.created_at, Category.updated_at]


class ProductAdmin(ModelView, model=Product):
    name = "Товар"
    name_plural = "Товары"
    column_list = [Product.name, Product.price, Product.is_active, Product.category]
    column_searchable_list = [Product.name]
    column_sortable_list = [Product.price]
    form_excluded_columns = [Product.created_at, Product.updated_at]


class OrderAdmin(ModelView, model=Order):
    name = "Заказ"
    name_plural = "Заказы"
    column_list = [Order.id, Order.email, Order.total, Order.status, Order.created_at]
    column_searchable_list = [Order.email]
    column_sortable_list = [Order.created_at, Order.total]
    can_create = False
    can_edit = True


class OrderItemAdmin(ModelView, model=OrderItem):
    name = "Позиция заказа"
    name_plural = "Позиции заказов"
    column_list = [OrderItem.product_name, OrderItem.price, OrderItem.quantity]
    can_create = False
    can_edit = False


class ProductVariantAdmin(ModelView, model=ProductVariant):
    name = "Вариант товара"
    name_plural = "Варианты товаров"
    column_list = [ProductVariant.product, ProductVariant.size, ProductVariant.stock]
    form_excluded_columns = [ProductVariant.created_at, ProductVariant.updated_at]


class ProductImageAdmin(ModelView, model=ProductImage):
    name = "Фото товара"
    name_plural = "Фото товаров"
    column_list = [ProductImage.product, ProductImage.path, ProductImage.position]
    form_excluded_columns = [ProductImage.created_at, ProductImage.updated_at]


class ReviewAdmin(ModelView, model=Review):
    name = "Отзыв"
    name_plural = "Отзывы"
    column_list = [Review.product, Review.rating, Review.is_approved, Review.created_at]
    column_sortable_list = [Review.created_at, Review.is_approved]
    form_excluded_columns = [Review.created_at, Review.updated_at]
    column_formatters = {Review.product: lambda m, a: m.product.name if m.product else ""}


class DashboardView(BaseView):
    name = "Аналитика"

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
