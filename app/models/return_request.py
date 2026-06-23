import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimeStampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.user import User


class ReturnRequest(UUIDMixin, TimeStampMixin, Base):
    __tablename__ = "return_requests"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Причина из фиксированного списка (см. service) + свободный комментарий
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # pending / approved / rejected / refunded
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

    # Ответ администратора (необязательно)
    admin_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # id платежа в YooKassa (копируется при создании заявки — чтобы
    # менеджер быстро нашёл платёж в кабинете YooKassa для возврата денег)
    payment_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    order: Mapped["Order"] = relationship("Order")
    user: Mapped["User"] = relationship("User")

    def __str__(self) -> str:
        return f"Возврат по заказу {self.order_id} — {self.status}"
