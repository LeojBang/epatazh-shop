from pydantic import BaseModel, EmailStr, Field


class CheckoutForm(BaseModel):
    email: EmailStr
    phone: str = Field(min_length=5, max_length=32)
    full_name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=5, max_length=1000)
