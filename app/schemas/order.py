from pydantic import BaseModel, EmailStr, Field


class CheckoutForm(BaseModel):
    email: EmailStr
    phone: str = Field(min_length=5, max_length=32)
    full_name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=5, max_length=1000)

    # --- Доставка СДЭК ---
    delivery_type: str = Field(default="pvz", max_length=16)
    cdek_city_code: int | None = None
    cdek_city_name: str | None = Field(default=None, max_length=255)
    cdek_pvz_code: str | None = Field(default=None, max_length=32)
    cdek_pvz_address: str | None = Field(default=None, max_length=1000)
