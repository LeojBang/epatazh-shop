from app.users import service
from app.schemas.user import UserCreate


class TestCreateUser:
    """Тесты создания пользователя."""

    async def test_password_is_hashed(self, db_session):
        """Пароль сохраняется хешированным, не в открытом виде."""
        user_in = UserCreate(
            email="test@example.com",
            password="secret123",
            full_name="Тест",
        )
        user = await service.create_user(db_session, user_in)

        assert user.email == "test@example.com"
        assert user.hashed_password != "secret123"  # не открытый текст
        assert user.id is not None  # получил id из базы

    async def test_get_user_by_email(self, db_session):
        """Созданного пользователя можно найти по email."""
        user_in = UserCreate(
            email="find@example.com", password="secret123", full_name="Поиск"
        )
        await service.create_user(db_session, user_in)

        found = await service.get_user_by_email(db_session, "find@example.com")
        assert found is not None
        assert found.email == "find@example.com"

    async def test_get_nonexistent_user(self, db_session):
        """Несуществующий email возвращает None."""
        found = await service.get_user_by_email(db_session, "nobody@example.com")
        assert found is None


class TestAuthentication:
    """Тесты аутентификации."""

    async def test_correct_credentials(self, db_session):
        """Верные email и пароль возвращают пользователя."""
        user_in = UserCreate(
            email="auth@example.com", password="secret123", full_name="Auth"
        )
        await service.create_user(db_session, user_in)

        user = await service.authenticate_user(
            db_session, "auth@example.com", "secret123"
        )
        assert user is not None
        assert user.email == "auth@example.com"

    async def test_wrong_password(self, db_session):
        """Неверный пароль возвращает None."""
        user_in = UserCreate(
            email="auth2@example.com", password="secret123", full_name="Auth"
        )
        await service.create_user(db_session, user_in)

        user = await service.authenticate_user(
            db_session, "auth2@example.com", "wrongpass"
        )
        assert user is None

    async def test_nonexistent_email(self, db_session):
        """Несуществующий email возвращает None."""
        user = await service.authenticate_user(
            db_session, "ghost@example.com", "secret123"
        )
        assert user is None


class TestChangePassword:
    """Тесты смены пароля."""

    async def test_correct_change(self, db_session):
        """Со старым верным паролем смена проходит."""
        user_in = UserCreate(
            email="pwd@example.com", password="oldpass123", full_name="Pwd"
        )
        user = await service.create_user(db_session, user_in)

        error = await service.change_password(
            db_session, user, "oldpass123", "newpass456"
        )
        assert error is None  # нет ошибки = успех

        # старый пароль больше не подходит, новый подходит
        assert (
            await service.authenticate_user(db_session, "pwd@example.com", "newpass456")
            is not None
        )
        assert (
            await service.authenticate_user(db_session, "pwd@example.com", "oldpass123")
            is None
        )

    async def test_wrong_current_password(self, db_session):
        """С неверным текущим паролем смена отклоняется."""
        user_in = UserCreate(
            email="pwd2@example.com", password="oldpass123", full_name="Pwd"
        )
        user = await service.create_user(db_session, user_in)

        error = await service.change_password(
            db_session, user, "wrongold", "newpass456"
        )
        assert error is not None  # есть ошибка
        assert "невер" in error.lower()  # про неверный пароль

    async def test_too_short_new_password(self, db_session):
        """Слишком короткий новый пароль отклоняется."""
        user_in = UserCreate(
            email="pwd3@example.com", password="oldpass123", full_name="Pwd"
        )
        user = await service.create_user(db_session, user_in)

        error = await service.change_password(db_session, user, "oldpass123", "short")
        assert error is not None
        assert "8" in error  # про минимум 8 символов


class TestUpdateProfile:
    """Тесты обновления профиля."""

    async def test_update_basic_fields(self, db_session):
        """Обновление имени, телефона, адреса."""
        user_in = UserCreate(
            email="prof@example.com", password="secret123", full_name="Старое"
        )
        user = await service.create_user(db_session, user_in)

        updated, error = await service.update_profile(
            db_session,
            user,
            full_name="Новое имя",
            email="prof@example.com",
            phone="+79001234567",
        )
        assert error is None
        assert updated.full_name == "Новое имя"
        assert updated.phone == "+79001234567"

    async def test_email_taken_by_another(self, db_session):
        """Нельзя сменить email на занятый другим пользователем."""
        # создаём двух пользователей
        await service.create_user(
            db_session,
            UserCreate(email="first@example.com", password="secret123", full_name="A"),
        )
        user_b = await service.create_user(
            db_session,
            UserCreate(email="second@example.com", password="secret123", full_name="B"),
        )

        # пытаемся дать второму email первого
        updated, error = await service.update_profile(
            db_session,
            user_b,
            full_name="B",
            email="first@example.com",
            phone=None,
        )
        assert updated is None
        assert error is not None  # email занят
