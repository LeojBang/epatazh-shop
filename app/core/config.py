from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Эпатаж"
    ENVIRONMENT: str = "local"
    DEBUG: bool = True

    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    REDIS_URL: str = "redis://localhost:6379/0"

    YOOKASSA_SHOP_ID: str
    YOOKASSA_SECRET_KEY: str

    # Код НДС для чеков (1 = без НДС/УСН, 3 = НДС 10%, 4 = НДС 20%)
    # Уточняется у заказчика по его системе налогообложения
    RECEIPT_VAT_CODE: int = 1

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


_INSECURE_SECRETS = {"", "your-secret-key-here", "change-me", "secret"}


def _validate_production(s: "Settings") -> None:
    """На проде не даём стартовать с небезопасными настройками."""
    if not s.is_production:
        return
    problems = []
    if s.SECRET_KEY in _INSECURE_SECRETS or len(s.SECRET_KEY) < 32:
        problems.append(
            "SECRET_KEY не задан или слишком короткий "
            '(сгенерируйте: python3 -c "import secrets; print(secrets.token_urlsafe(48))")'
        )
    if s.DEBUG:
        problems.append("DEBUG должен быть False на production")
    if (
        "your-shop-id" in s.YOOKASSA_SHOP_ID
        or "your-secret-key" in s.YOOKASSA_SECRET_KEY
    ):
        problems.append("YOOKASSA-ключи не настроены (стоят значения-заглушки)")
    if problems:
        raise RuntimeError(
            "Небезопасная production-конфигурация:\n  - " + "\n  - ".join(problems)
        )


settings = Settings()
_validate_production(settings)
