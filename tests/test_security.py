from app.core.security import hash_password, verify_password


class TestPasswordHashing:
    """Тесты хеширования паролей."""

    def test_hash_is_not_plaintext(self):
        """Хеш не равен исходному паролю."""
        password = "mysecret123"
        hashed = hash_password(password)
        assert hashed != password
        assert len(hashed) > 20  # bcrypt-хеш длинный

    def test_verify_correct_password(self):
        """Верный пароль проходит проверку."""
        password = "mysecret123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        """Неверный пароль не проходит."""
        hashed = hash_password("mysecret123")
        assert verify_password("wrongpassword", hashed) is False

    def test_same_password_different_hashes(self):
        """Один пароль даёт разные хеши (соль) — но оба валидны."""
        password = "mysecret123"
        h1 = hash_password(password)
        h2 = hash_password(password)
        assert h1 != h2  # соль делает хеши разными
        assert verify_password(password, h1)
        assert verify_password(password, h2)