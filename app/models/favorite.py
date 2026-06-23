import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimeStampMixin, UUIDMixin


class Favorite(UUIDMixin, TimeStampMixin, Base):
    __tablename__ = "favorites"
    __table_args__ = (
        # Один товар у пользователя может быть в избранном только раз
        UniqueConstraint("user_id", "product_id", name="uq_favorite_user_product"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
