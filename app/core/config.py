"""
app/core/config.py
==================
Pydantic Settings yordamida .env fayldan
barcha konfiguratsiya sozlamalarini o'qish.

Ishlatish:
    from app.core.config import settings
    print(settings.DATABASE_URL)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """
    Ilova sozlamalari klassı.
    Barcha qiymatlar .env fayldan yoki muhit o'zgaruvchilaridan o'qiladi.
    """

    # --- Ilova ma'lumotlari ---
    APP_NAME: str = "Elektron Hisob-Faktura Tizimi"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # --- Ma'lumotlar bazasi ---
    # Render.com'da DATABASE_URL muhit o'zgaruvchisi sifatida beriladi
    DATABASE_URL: str

    # --- Xavfsizlik ---
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Birinchi Admin (ixtiyoriy, faqat ilk deploy uchun) ---
    FIRST_ADMIN_LOGIN   : str = "admin"
    FIRST_ADMIN_PASSWORD: str = "Admin@12345"
    FIRST_ADMIN_NAME    : str = "Bosh Administrator"

    # --- CORS ---
    # Vergul bilan ajratilgan manzillar: "http://localhost:3000,https://myfrontend.com"
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # --- Server ---
    PORT: int = 8000

    # Pydantic v2 konfiguratsiyasi: .env faylni avtomatik o'qiydi
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # .env dagi noma'lum o'zgaruvchilarni e'tiborsiz qoldirish
    )

    @property
    def allowed_origins_list(self) -> list[str]:
        """ALLOWED_ORIGINS stringini ro'yxatga aylantiradi."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]


@lru_cache()
def get_settings() -> Settings:
    """
    Sozlamalarni keshga olib qaytaradi.
    lru_cache — har safar yangi obyekt yaratmasdan keshdan qaytaradi.
    """
    return Settings()


# Global sozlamalar obyekti — barcha modullar ushbu obyektni import qiladi
settings = get_settings()
