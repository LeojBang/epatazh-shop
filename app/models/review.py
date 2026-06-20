import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimeStampMixin, UUIDMixin


class Review(UUIDMixin, TimeStampMixin, Base):
    __tablename__ = "reviews"
    # Один пользователь — один отзыв на товар
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_review_user_product"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship()  # noqa: F821
    product: Mapped["Product"] = relationship()  # noqa: F821

    def __str__(self) -> str:
        return f"Отзыв {self.rating}★"