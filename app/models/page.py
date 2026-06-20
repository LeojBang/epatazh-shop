from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimeStampMixin, UUIDMixin


class InfoPage(UUIDMixin, TimeStampMixin, Base):
    __tablename__ = "info_pages"

    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # колонка футера: information / company / cooperation
    footer_group: Mapped[str | None] = mapped_column(String(50), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __str__(self) -> str:
        return self.title