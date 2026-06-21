from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.payment import Payment

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimeStampMixin, UUIDMixin


class Order(UUIDMixin, TimeStampMixin, Base):
    __tablename__ = "orders"

    # user_id может быть NULL — заказы гостей без аккаунта
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # контакты и адрес
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"Заказ {self.email} — {self.total} ₽"


class OrderItem(UUIDMixin, TimeStampMixin, Base):
    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_variants.id"), nullable=True
    )
    size: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # снимок данных товара на момент покупки
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")

    def __str__(self) -> str:
        return f"{self.product_name} × {self.quantity}"
