"""
app/core/database.py
=====================
SQLAlchemy yordamida ma'lumotlar bazasiga ulanishni sozlash.

Lokal ishlab chiqish: SQLite  (fayl avtomatik yaratiladi)
Render.com (production): PostgreSQL

Yaratilgan obyektlar:
    - engine        : Ma'lumotlar bazasi ulanish mexanizmi
    - SessionLocal  : Har bir so'rov uchun alohida sessiya
    - Base          : Barcha modellar meros oluvchi asosiy klass
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings

# Logging sozlash
logger = logging.getLogger(__name__)

# ============================================================
# Ma'lumotlar bazasi ulanish mexanizmini yaratish (Engine)
# SQLite (lokal) va PostgreSQL (production) farqli sozlamalar
# ============================================================
try:
    _db_url = settings.DATABASE_URL

    if _db_url.startswith("sqlite"):
        # SQLite uchun — fayl avtomatik yaratiladi, pool kerak emas
        engine = create_engine(
            _db_url,
            connect_args={"check_same_thread": False},
            echo=settings.DEBUG,
        )
        logger.info("✅ SQLite engine yaratildi (lokal ishlab chiqish).")
    else:
        # PostgreSQL uchun — Render.com va production
        engine = create_engine(
            _db_url,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
            echo=settings.DEBUG,
        )
        logger.info("✅ PostgreSQL engine yaratildi.")

except Exception as e:
    logger.critical(f"❌ Engine yaratishda xatolik: {e}")
    raise

# ============================================================
# Sessiya zavodi (Session Factory)
# ============================================================
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,  # O'zgarishlar faqat session.commit() bilan saqlanadi
    autoflush=False,   # O'zgarishlar faqat so'ralganda flush qilinadi
    expire_on_commit=False,  # Commit'dan keyin obyektlar sessiyada saqlanadi
)

# ============================================================
# Asosiy model klassı (Deklarativ Base)
# ============================================================
# Barcha model klasslari: class MyModel(Base): ...
Base = declarative_base()


# ============================================================
# Dependency Injection — FastAPI endpoint'larda sessiya olish
# ============================================================
def get_db():
    """
    FastAPI'ning Depends() bilan ishlaydigan generator funksiya.
    Har bir HTTP so'rovi uchun alohida ma'lumotlar bazasi sessiyasi ochadi,
    so'rov tugagach sessiyani yopadi (xatolik bo'lsa ham).

    Ishlatish:
        from fastapi import Depends
        from app.core.database import get_db
        from sqlalchemy.orm import Session

        @app.get("/items/")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"❌ Sessiya xatoligi: {e}")
        db.rollback()  # Xatolik bo'lsa o'zgarishlarni bekor qilish
        raise
    finally:
        db.close()  # Sessiyani har doim yopish (xatolik bo'lsa ham)


# ============================================================
# Ma'lumotlar bazasi ulanishini tekshirish funksiyasi
# ============================================================
def check_database_connection() -> dict:
    """
    Ma'lumotlar bazasiga ulanishni tekshiradi.
    Ilova ishga tushganda va health-check endpoint'da ishlatiladi.

    Qaytaradi:
        dict: Ulanish holati va xabar
    """
    try:
        with engine.connect() as connection:
            # Oddiy SQL so'rov orqali ulanishni tekshirish
            result = connection.execute(text("SELECT 1"))
            result.fetchone()
        logger.info("✅ PostgreSQL ulanishi muvaffaqiyatli!")
        return {"status": "ok", "message": "Ma'lumotlar bazasi bilan ulanish muvaffaqiyatli."}

    except SQLAlchemyError as e:
        logger.error(f"❌ Ma'lumotlar bazasiga ulanib bo'lmadi: {e}")
        return {"status": "error", "message": f"Ulanish xatoligi: {str(e)}"}
