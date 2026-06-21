from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
    user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hash_password(user_in.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


async def update_profile(
    db: AsyncSession,
    user: User,
    *,
    full_name: str | None,
    email: str,
    phone: str | None,
    address: str | None,
) -> tuple[User | None, str | None]:
    """Обновляет профиль. Возвращает (user, error)."""
    # Если email меняется — проверяем, что он не занят другим пользователем
    if email != user.email:
        existing = await get_user_by_email(db, email)
        if existing and existing.id != user.id:
            return None, "Этот email уже занят другим пользователем"

    user.full_name = full_name or None
    user.email = email
    user.phone = phone or None
    user.address = address or None
    await db.commit()
    await db.refresh(user)
    return user, None


async def change_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
) -> str | None:
    """Меняет пароль. Возвращает текст ошибки или None при успехе."""
    from app.core.security import verify_password, hash_password

    if not verify_password(current_password, user.hashed_password):
        return "Текущий пароль неверён"
    if len(new_password) < 8:
        return "Новый пароль должен быть не короче 8 символов"

    user.hashed_password = hash_password(new_password)
    await db.commit()
    return None
