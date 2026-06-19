from sqladmin import ModelView

from app.models.catalog import Category, Product
from app.models.order import Order, OrderItem
from app.models.user import User


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
    column_list = [Product.name, Product.price, Product.stock, Product.is_active, Product.category]
    column_searchable_list = [Product.name]
    column_sortable_list = [Product.price, Product.stock]
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
