import asyncio
import getpass

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User


async def create_admin():
    print("Создание администратора")
    email = input("Email: ").strip()
    password = getpass.getpass("Пароль: ")
    full_name = input("Имя: ").strip()

    if len(password) < 8:
        print("Пароль должен быть не короче 8 символов.")
        return

    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == email))
        if existing:
            print(f"Пользователь {email} уже существует.")
            return

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name or None,
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        await db.commit()
        print(f"Администратор {email} создан.")


if __name__ == "__main__":
    asyncio.run(create_admin())