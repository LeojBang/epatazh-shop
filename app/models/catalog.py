import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimeStampMixin, UUIDMixin


class Category(UUIDMixin, TimeStampMixin, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)

    products: Mapped[list["Product"]] = relationship(back_populates="category")

    def __str__(self) -> str:
        return self.name


class Product(UUIDMixin, TimeStampMixin, Base):
    __tablename__ = "products"

    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    material: Mapped[str | None] = mapped_column(String(255), nullable=True)
    care: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    badge: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped["Category"] = relationship(back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.position",
    )
    colors: Mapped[list["ProductColor"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductColor.position",
    )

    @property
    def effective_price(self) -> Decimal:
        """Цена с учётом скидки: sale_price если задана и ниже обычной, иначе price."""
        if self.sale_price is not None and self.sale_price < self.price:
            return self.sale_price
        return self.price

    def __str__(self) -> str:
        return self.name


class ProductVariant(UUIDMixin, TimeStampMixin, Base):
    __tablename__ = "product_variants"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False
    )
    size: Mapped[str] = mapped_column(String(32), nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="variants")

    def __str__(self) -> str:
        return f"Размер {self.size}"


class ProductImage(UUIDMixin, TimeStampMixin, Base):
    __tablename__ = "product_images"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="images")

    def __str__(self) -> str:
        return self.path


class ProductColor(UUIDMixin, TimeStampMixin, Base):
    """Цветовой вариант товара (например: Чёрный #000000)."""

    __tablename__ = "product_colors"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # «Чёрный»
    hex: Mapped[str] = mapped_column(String(7), nullable=False)  # «#000000»
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="colors")
    images: Mapped[list["ProductColorImage"]] = relationship(
        back_populates="color",
        cascade="all, delete-orphan",
        order_by="ProductColorImage.position",
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.hex})"


class ProductColorImage(UUIDMixin, TimeStampMixin, Base):
    """Фото для конкретного цветового варианта."""

    __tablename__ = "product_color_images"

    color_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_colors.id"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    color: Mapped["ProductColor"] = relationship(back_populates="images")

    def __str__(self) -> str:
        return self.path
