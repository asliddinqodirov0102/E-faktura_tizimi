"""
app/core/security.py
=====================
Tizim xavfsizligining yadrosı:
    1. Parollarni bcrypt bilan heshlash va tekshirish
    2. JWT access token yaratish va dekodlash
    3. Faktura raqamini avtomatik generatsiya qilish

Ishlatish:
    from app.core.security import hash_password, verify_password, create_access_token
"""

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ============================================================
#  PAROL HESHLASH (bcrypt)
# ============================================================

# bcrypt — hozirgi eng xavfsiz parol heshlash algoritmi
# deprecated="auto" → eski algoritmlar avtomatik yangilanadi
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    Oddiy matn parolni bcrypt bilan heshlaydi.
    Heshdan original parolni tiklab bo'lmaydi (bir tomonlama).

    Args:
        plain_password: Foydalanuvchi kiritgan ochiq parol

    Returns:
        str: bcrypt heshi (ma'lumotlar bazasiga saqlanadi)

    Misol:
        hashed = hash_password("Xavfsiz@2024")
        # → "$2b$12$..."
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Foydalanuvchi kiritgan parolni ma'lumotlar bazasidagi hesh bilan solishtiradi.

    Args:
        plain_password   : Login paytida kiritilgan ochiq parol
        hashed_password  : Ma'lumotlar bazasida saqlangan hesh

    Returns:
        bool: Parol to'g'ri bo'lsa True, aks holda False
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        # Noto'g'ri hesh formati yoki boshqa xatoliklar — False qaytariladi
        return False


# ============================================================
#  JWT TOKEN (JSON Web Token)
# ============================================================

def create_access_token(
    subject: int,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    JWT access token yaratadi.

    Token ichiga nima yoziladi:
        - sub  : Foydalanuvchi ID si (string formatida)
        - role : Foydalanuvchi roli ("admin", "kassir", "omborchi")
        - exp  : Token muddati tugash vaqti (UTC)
        - iat  : Token yaratilgan vaqt (UTC)

    Args:
        subject       : Foydalanuvchi ID (integer)
        role          : Foydalanuvchi roli (string)
        expires_delta : Token amal qilish muddati (None bo'lsa config.py dan olinadi)

    Returns:
        str: Imzolangan JWT token string

    Misol:
        token = create_access_token(subject=1, role="admin")
    """
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub"  : str(subject),   # 'sub' (subject) — JWT standartiga ko'ra user ID
        "role" : role,           # Rol tekshirish uchun
        "iat"  : now,            # Issued At — yaratilgan vaqt
        "exp"  : expire,         # Expiration — amal qilish muddati
    }

    token = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return token


def decode_access_token(token: str) -> Optional[dict]:
    """
    JWT tokenni tekshiradi va ichidagi ma'lumotlarni qaytaradi.
    Token noto'g'ri yoki muddati o'tgan bo'lsa None qaytaradi.

    Args:
        token: Bearer token string (Authorization headerdan olingan)

    Returns:
        dict | None: Token payload yoki None (xatolik bo'lsa)

    Payload misoli:
        {"sub": "1", "role": "admin", "iat": ..., "exp": ...}
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError:
        # Imzo noto'g'ri, muddati o'tgan yoki boshqa JWT xatoligi
        return None


# ============================================================
#  FAKTURA RAQAMI GENERATORI
# ============================================================

def generate_invoice_number() -> str:
    """
    Noyob faktura raqamini avtomatik generatsiya qiladi.

    Format: INV-YYYY-XXXXXX
        - YYYY  : Joriy yil (to'rt raqam)
        - XXXXXX: 6 ta tasodifiy katta harf va raqam

    Returns:
        str: Noyob faktura raqami, masalan: "INV-2024-A3K9PZ"

    Eslatma:
        Bu funksiya UUID yoki ma'lumotlar bazasi sequence o'rniga
        ishlatilishi mumkin. Agar to'qnashuv ehtimoli muhim bo'lsa,
        ma'lumotlar bazasida UNIQUE constraint bilan qo'shib ishlatiladi.
    """
    year = datetime.now(timezone.utc).year
    alphabet = string.ascii_uppercase + string.digits
    random_suffix = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"INV-{year}-{random_suffix}"
