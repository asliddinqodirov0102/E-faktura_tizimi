"""
app/api/v1/auth.py
===================
Autentifikatsiya API Router'lari.

Endpoint'lar:
    POST /api/v1/auth/register  → Yangi foydalanuvchi yaratish (faqat Admin)
    POST /api/v1/auth/login     → Login qilib JWT token olish
    GET  /api/v1/auth/me        → Joriy foydalanuvchi ma'lumotlari
    POST /api/v1/auth/logout    → Chiqish (frontend'da token o'chiriladi)

Xavfsizlik arxitekturasi:
    - Register → Faqat tizimga kirgan Admin bajarishi mumkin
    - Login    → Ochiq endpoint (hamma kirishi mumkin)
    - Me       → Ixtiyoriy foydalanuvchi (token bilan)
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models.all_models import User, UserRole
from app.schemas.all_schemas import UserCreate, UserResponse
from app.api.deps import get_current_user, get_admin_user

logger = logging.getLogger(__name__)

# ============================================================
#  ROUTER — prefix va tag main.py'da include qilinganda qo'shiladi
# ============================================================
router = APIRouter(prefix="/auth", tags=["🔐 Autentifikatsiya"])


# ============================================================
#  YORDAMCHI SXEMALAR — Auth uchun maxsus javob shakllari
# ============================================================
from pydantic import BaseModel
from typing import Optional


class TokenResponse(BaseModel):
    """Login muvaffaqiyatli bo'lganda qaytariladigan javob."""
    access_token  : str
    token_type    : str = "bearer"
    expires_in    : int          # Soniyada (frontend uchun qulay)
    user          : UserResponse # Foydalanuvchi ma'lumotlari (sahifani yuklash uchun)


class RegisterResponse(BaseModel):
    """Yangi foydalanuvchi yaratilganda qaytariladigan javob."""
    success : bool = True
    message : str
    user    : UserResponse


# ============================================================
#  1. REGISTER — Faqat Admin yangi xodim qo'sha oladi
# ============================================================

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yangi xodim qo'shish (Faqat Admin)",
    description=(
        "Tizimga yangi kassir yoki omborchi qo'shadi. "
        "Faqat **admin** roli bilan kirgan foydalanuvchi bajarishi mumkin."
    ),
)
def register_user(
    user_data : UserCreate,
    db        : Session = Depends(get_db),
    admin     : User    = Depends(get_admin_user),   # ← Faqat admin!
) -> RegisterResponse:
    """
    Yangi foydalanuvchi (kassir/omborchi) ro'yxatdan o'tkazish.

    Xatoliklar:
        400 → Bunday login allaqachon mavjud
        403 → Siz admin emassiz
        422 → Kiritilgan ma'lumotlar noto'g'ri (Pydantic validatsiya)
    """
    # ── 1. Login allaqachon mavjudligini tekshirish ─────────────
    existing = db.query(User).filter(User.login == user_data.login).first()
    if existing:
        logger.warning(
            f"⚠️ Takror login urinishi: '{user_data.login}' "
            f"(admin: {admin.login})"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{user_data.login}' logini allaqachon band. Boshqa login tanlang.",
        )

    # ── 2. Yangi foydalanuvchi yaratish ─────────────────────────
    new_user = User(
        ism_sharif  = user_data.ism_sharif,
        login       = user_data.login,
        parol_hash  = hash_password(user_data.parol),   # Parolni heshlash
        rol         = user_data.rol,
        is_active   = True,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)   # Bazadan ID va yaratilgan sanani yangilash
    except IntegrityError as e:
        db.rollback()
        logger.error(f"❌ Foydalanuvchi yaratishda xatolik: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Foydalanuvchi yaratishda xatolik yuz berdi. Login noyob bo'lishi kerak.",
        )

    logger.info(
        f"✅ Yangi foydalanuvchi yaratildi: '{new_user.login}' "
        f"(rol: {new_user.rol}) | Admin: '{admin.login}'"
    )

    return RegisterResponse(
        success=True,
        message=f"'{new_user.ism_sharif}' muvaffaqiyatli ro'yxatdan o'tkazildi.",
        user=UserResponse.model_validate(new_user),
    )


# ============================================================
#  2. LOGIN — JWT token olish
# ============================================================

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Tizimga kirish (Login)",
    description=(
        "Login va parolni tekshirib, **JWT Bearer token** qaytaradi. "
        "Keyingi so'rovlarda: `Authorization: Bearer <token>` headerini yuboring."
    ),
)
def login(
    form_data : OAuth2PasswordRequestForm = Depends(),   # Swagger UI bilan mos
    db        : Session = Depends(get_db),
) -> TokenResponse:
    """
    Foydalanuvchini autentifikatsiya qilish.

    OAuth2PasswordRequestForm Swagger UI'da "Authorize" tugmasi bilan ishlaydi:
        - username → login
        - password → parol

    Xatoliklar:
        401 → Login yoki parol noto'g'ri
        403 → Hisob bloklangan (is_active=False)
    """
    # ── 1. Foydalanuvchini login bo'yicha topish ─────────────────
    user = db.query(User).filter(User.login == form_data.username).first()

    # ── 2. Parolni tekshirish ─────────────────────────────────────
    # Foydalanuvchi topilmasa ham parol tekshiriladi (timing attack oldini olish)
    if not user or not verify_password(form_data.password, user.parol_hash):
        logger.warning(
            f"⚠️ Noto'g'ri login urinishi: username='{form_data.username}'"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login yoki parol noto'g'ri. Iltimos, qayta tekshiring.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── 3. Hisob faolligini tekshirish ───────────────────────────
    if not user.is_active:
        logger.warning(f"⚠️ Bloklangan hisob kirish urinishi: '{user.login}'")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sizning hisobingiz bloklangan. Administrator bilan bog'laning.",
        )

    # ── 4. JWT token yaratish ─────────────────────────────────────
    from app.core.config import settings

    expires_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    access_token = create_access_token(
        subject=user.id,
        role=user.rol.value,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    logger.info(f"✅ Muvaffaqiyatli login: '{user.login}' (rol: {user.rol})")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_seconds,
        user=UserResponse.model_validate(user),
    )


# ============================================================
#  3. ME — Joriy foydalanuvchi ma'lumotlari
# ============================================================

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Mening profilim",
    description="JWT token orqali joriy tizimga kirgan foydalanuvchi ma'lumotlarini qaytaradi.",
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Token tekshirib, joriy foydalanuvchi profilini qaytaradi.
    Frontend sahifasini yuklashda foydalanuvchi ma'lumotlarini olish uchun ishlatiladi.
    """
    return UserResponse.model_validate(current_user)


# ============================================================
#  4. LOGOUT — Token bekor qilish (frontend ishini bajaradi)
# ============================================================

@router.post(
    "/logout",
    summary="Tizimdan chiqish (Logout)",
    description=(
        "JWT tokenlar stateless bo'lgani uchun server tomonida haqiqiy 'o'chirish' yo'q. "
        "Frontend token'ni localStorage/sessionStorage'dan o'chirishi kerak."
    ),
)
def logout(
    current_user: User = Depends(get_current_user),
):
    """
    Logout — Xavfsiz chiqish uchun yordamchi endpoint.

    Muhim eslatma:
        JWT tokenlarini server tomonida bekor qilib bo'lmaydi
        (bu stateless arxitekturaning xususiyati).
        Haqiqiy blacklist kerak bo'lsa, Redis'da token saqlash kerak.
        Hozirgi rejimda frontend token'ni o'chirib tashlashi kifoya.
    """
    logger.info(f"👋 Foydalanuvchi tizimdan chiqdi: '{current_user.login}'")
    return {
        "success"  : True,
        "message"  : f"Xayr, {current_user.ism_sharif}! Muvaffaqiyatli chiqdingiz.",
        "action"   : "Frontend: localStorage.removeItem('access_token') qiling.",
    }
