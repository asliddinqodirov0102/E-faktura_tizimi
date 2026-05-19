"""
app/api/deps.py
================
FastAPI Dependency Injection funksiyalari.

Bu faylda:
    1. Ma'lumotlar bazasi sessiyasini boshqarish (get_db)
    2. JWT tokendan joriy foydalanuvchini aniqlash (get_current_user)
    3. Rol asosida kirish huquqini tekshirish (require_role factory)

Ishlatish:
    from app.api.deps import get_current_user, get_admin_user

    @router.get("/admin-only")
    def admin_endpoint(user = Depends(get_admin_user)):
        ...
"""

import logging
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.all_models import User, UserRole

logger = logging.getLogger(__name__)

# ============================================================
#  OAuth2 sxemasi — Swagger UI uchun "Authorize" tugmasi chiqaradi
#  tokenUrl → login endpoint manzili (Swagger UI foydalanadi)
# ============================================================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ============================================================
#  JORIY FOYDALANUVCHINI ANIQLASH
# ============================================================

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Authorization headeridagi Bearer tokenni tekshirib,
    ma'lumotlar bazasidan joriy foydalanuvchini topadi.

    Xatolik holatlari:
        401 Unauthorized → Token yo'q, noto'g'ri yoki muddati o'tgan
        401 Unauthorized → Foydalanuvchi ID token ichida yo'q
        401 Unauthorized → Foydalanuvchi bazada topilmadi yoki bloklangan

    Returns:
        User: Joriy tizimga kirgan foydalanuvchi ORM obyekti
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kirish huquqi yo'q. Token noto'g'ri yoki muddati tugagan.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Tokenni dekodlash
    payload = decode_access_token(token)
    if payload is None:
        logger.warning("❌ Token dekodlashda xatolik yoki muddati o'tgan.")
        raise credentials_exception

    # 2. Foydalanuvchi ID sini olish ('sub' field)
    user_id_str: str | None = payload.get("sub")
    if user_id_str is None:
        logger.warning("❌ Token ichida 'sub' (user ID) maydoni yo'q.")
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        logger.warning(f"❌ Token 'sub' maydoni integer emas: {user_id_str}")
        raise credentials_exception

    # 3. Ma'lumotlar bazasidan foydalanuvchini topish
    user = (
        db.query(User)
        .filter(User.id == user_id, User.is_active == True)  # noqa: E712
        .first()
    )

    if user is None:
        logger.warning(f"❌ Foydalanuvchi topilmadi yoki bloklangan: id={user_id}")
        raise credentials_exception

    return user


# ============================================================
#  ROL TEKSHIRISH FACTORY (Higher-Order Function)
# ============================================================

def require_role(*roles: UserRole) -> Callable:
    """
    Berilgan rollarga ega foydalanuvchilarga kirish ruxsatini beruvchi
    dependency factory funksiyasi.

    Args:
        *roles: Ruxsat etilgan bir yoki bir nechta UserRole

    Returns:
        Dependency funksiyasi — endpoint'larda Depends() bilan ishlatiladi

    Misol:
        # Faqat adminlar uchun
        @router.delete("/user/{id}")
        def delete_user(user = Depends(require_role(UserRole.admin))):
            ...

        # Admin yoki kassirlar uchun
        @router.post("/invoice")
        def create_invoice(user = Depends(require_role(UserRole.admin, UserRole.kassir))):
            ...
    """
    def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.rol not in roles:
            allowed = [r.value for r in roles]
            logger.warning(
                f"⛔ Ruxsat rad etildi: user_id={current_user.id}, "
                f"rol='{current_user.rol}', kerakli rollar={allowed}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Bu amalni bajarish uchun ruxsat yo'q. "
                    f"Kerakli rol(lar): {', '.join(allowed)}."
                ),
            )
        return current_user

    return role_checker


# ============================================================
#  TAYYOR DEPENDENCY'LAR — Endpoint'larda to'g'ridan-to'g'ri ishlatiladi
# ============================================================

# Faqat Admin huquqi kerak bo'lgan endpointlar uchun
get_admin_user = require_role(UserRole.admin)

# Admin yoki Kassir kirishi mumkin bo'lgan endpointlar uchun
get_kassir_or_admin = require_role(UserRole.admin, UserRole.kassir)

# Admin yoki Omborchi kirishi mumkin bo'lgan endpointlar uchun
get_omborchi_or_admin = require_role(UserRole.admin, UserRole.omborchi)


# ============================================================
#  RE-EXPORT — get_db ni deps.py orqali ham olish mumkin
# ============================================================
# (Bu qulaylik uchun, bevosita database.py'dan ham import qilish mumkin)
__all__ = [
    "get_db",
    "get_current_user",
    "require_role",
    "get_admin_user",
    "get_kassir_or_admin",
    "get_omborchi_or_admin",
    "oauth2_scheme",
]
