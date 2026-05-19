"""
setup_db.py
============
Loyihani birinchi marta ishga tushirishdan OLDIN bajariladigan skript.

Bu skript:
  1. .env fayldan DATABASE_URL ni o'qiydi
  2. PostgreSQL'ga ulanadi
  3. Baza mavjud bo'lmasa, avtomatik yaratadi
  4. Muvaffaqiyat yoki xatolik haqida xabar beradi

Ishlatish:
    python setup_db.py
"""

import sys
from urllib.parse import urlparse

from dotenv import load_dotenv
import os

# .env faylni yuklash
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    print("❌ .env faylda DATABASE_URL topilmadi!")
    print("   .env.example faylni nusxalab .env yarating va to'ldiring.")
    sys.exit(1)

# DATABASE_URL ni tahlil qilish
# Format: postgresql://user:password@host:port/dbname
try:
    parsed     = urlparse(DATABASE_URL)
    db_user    = parsed.username
    db_pass    = parsed.password
    db_host    = parsed.hostname or "localhost"
    db_port    = parsed.port    or 5432
    db_name    = parsed.path.lstrip("/")   # /efaktura_db → efaktura_db
except Exception as e:
    print(f"❌ DATABASE_URL formati noto'g'ri: {e}")
    print("   To'g'ri format: postgresql://postgres:parol@localhost:5432/efaktura_db")
    sys.exit(1)

print(f"\n{'='*50}")
print(f"  E-Faktura Tizimi — Baza Sozlash")
print(f"{'='*50}")
print(f"  Host    : {db_host}:{db_port}")
print(f"  Foydalanuvchi: {db_user}")
print(f"  Baza    : {db_name}")
print(f"{'='*50}\n")

# psycopg2 orqali ulanish
try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    print("❌ psycopg2 o'rnatilmagan. Quyidagi buyruqni bajaring:")
    print("   pip install psycopg2-binary")
    sys.exit(1)

# ── 'postgres' default bazasiga ulanib, yangi baza yaratish ──
# (PostgreSQL'da yangi baza yaratish uchun boshqa bazaga ulanish kerak)
try:
    conn = psycopg2.connect(
        host     = db_host,
        port     = db_port,
        user     = db_user,
        password = db_pass,
        database = "postgres",    # Default PostgreSQL bazasi (har doim mavjud)
        connect_timeout = 10,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    # Baza allaqachon mavjudligini tekshirish
    cursor.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s",
        (db_name,)
    )
    exists = cursor.fetchone()

    if exists:
        print(f"ℹ️  '{db_name}' bazasi allaqachon mavjud. Yangi yaratilmadi.")
    else:
        # Bazani yaratish (SQL injection xavfsizligi uchun sql.Identifier)
        cursor.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name))
        )
        print(f"✅ '{db_name}' bazasi muvaffaqiyatli yaratildi!")

    cursor.close()
    conn.close()

except psycopg2.OperationalError as e:
    print(f"❌ PostgreSQL'ga ulanib bo'lmadi!")
    print(f"   Xato: {e}")
    print("\n   Tekshiring:")
    print("   1. PostgreSQL xizmati ishlamoqdami? (Services → postgresql)")
    print("   2. .env fayldagi DATABASE_URL to'g'rimi?")
    print("   3. Foydalanuvchi nomi va parol to'g'rimi?")
    sys.exit(1)

except psycopg2.Error as e:
    print(f"❌ Baza yaratishda xatolik: {e}")
    sys.exit(1)

# ── Jadvallarni yaratish (SQLAlchemy orqali) ─────────────────
print("\n⚙️  Jadvallar yaratilmoqda...")
try:
    from app.core.database import engine, Base
    import app.models.all_models   # noqa — modellarni ro'yxatga olish

    Base.metadata.create_all(bind=engine)
    print("✅ Barcha jadvallar muvaffaqiyatli yaratildi!")

except Exception as e:
    print(f"❌ Jadvallar yaratishda xatolik: {e}")
    sys.exit(1)

print(f"\n{'='*50}")
print("  ✅ SOZLASH MUVAFFAQIYATLI YAKUNLANDI!")
print("  Endi serverni ishga tushiring:")
print("  uvicorn app.main:app --reload --port 8000")
print(f"{'='*50}\n")
