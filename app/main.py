"""
app/main.py
============
FastAPI ilovasining asosiy kirish nuqtasi.

Bu fayl:
  - FastAPI ilovasini yaratadi
  - CORS sozlaydi
  - Router'larni ulaydi
  - Ilova ishga tushganda bazani tekshiradi
  - Asosiy "/" va "/health" endpoint'larni ta'minlaydi
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import check_database_connection, engine, Base, SessionLocal
from app.core.security import hash_password

# Barcha modellarni import qilish (Base.metadata.create_all uchun zarur)
import app.models.all_models  # noqa: F401 — modellarni ro'yxatga olish
from app.models.all_models import User, UserRole

# API Router'larni import qilish
from app.api.v1 import auth      as auth_router
from app.api.v1 import products  as products_router
from app.api.v1 import inventory as inventory_router
from app.api.v1 import customers as customers_router
from app.api.v1 import invoices  as invoices_router

# Logging sozlash
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
# Ilova hayot sikli: Ishga tushish va to'xtash hodisalari
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Ilova ishga tushganda va yopilganda bajariladigan kod.
    Ma'lumotlar bazasi ulanishini ishga tushishda tekshiradi.
    """
    # ---- Ishga tushish ----
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} ishga tushmoqda...")

    db_status = check_database_connection()
    if db_status["status"] == "ok":
        logger.info("✅ PostgreSQL bazasiga ulanish muvaffaqiyatli.")

        # ── Jadvallarni avtomatik yaratish ──────────────────────
        # Development uchun qulay. Production'da Alembic ishlating!
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Jadvallar tekshirildi / yaratildi.")

        # ── Birinchi Admin yaratish (agar tizimda hech kim yo'q bo'lsa) ──
        _seed_initial_admin()
    else:
        logger.warning(f"⚠️ PostgreSQL bazasiga ulanishda muammo: {db_status['message']}")

    yield  # Ilova ishlaydi

    # ---- To'xtash ----
    logger.info(f"🛑 {settings.APP_NAME} to'xtatilmoqda...")


def _seed_initial_admin() -> None:
    """
    Tizimda hech qanday foydalanuvchi bo'lmasa,
    .env fayldan sozlamalarni o'qib birinchi admin yaratadi.

    .env ga qo'shing:
        FIRST_ADMIN_LOGIN=admin
        FIRST_ADMIN_PASSWORD=Admin@12345
        FIRST_ADMIN_NAME=Bosh Administrator
    """
    # Konfiguratsiyadan birinchi admin ma'lumotlarini olish
    admin_login    = getattr(settings, "FIRST_ADMIN_LOGIN",    "admin")
    admin_password = getattr(settings, "FIRST_ADMIN_PASSWORD", "Admin@12345")
    admin_name     = getattr(settings, "FIRST_ADMIN_NAME",     "Bosh Administrator")

    db = SessionLocal()
    try:
        # Tizimda admin mavjudligini tekshirish
        existing_admin = db.query(User).filter(
            User.rol == UserRole.admin
        ).first()

        if existing_admin:
            logger.info(f"ℹ️ Admin allaqachon mavjud: '{existing_admin.login}'. Seed o'tkazib yuborildi.")
            return

        # Birinchi adminni yaratish
        first_admin = User(
            ism_sharif = admin_name,
            login      = admin_login,
            parol_hash = hash_password(admin_password),
            rol        = UserRole.admin,
            is_active  = True,
        )
        db.add(first_admin)
        db.commit()
        logger.info(
            f"🌱 Birinchi admin yaratildi: login='{admin_login}' "
            f"| MUHIM: Parolni .env da o'zgartiring!"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Birinchi admin yaratishda xatolik: {e}")
    finally:
        db.close()


# ============================================================
# FastAPI ilovasini yaratish — To'liq O'zbekcha hujjatlar
# ============================================================

# Swagger UI'da ko'rinadigan bo'limlar tavsifi
tags_metadata = [
    {
        "name": "🔐 Autentifikatsiya",
        "description": (
            "Tizimga **kirish va chiqish** bo'limi.\n\n"
            "- **Login** → JWT token oling\n"
            "- **Register** → Yangi xodim qo'shing *(faqat Admin)*\n"
            "- **Me** → O'z profilingizni ko'ring\n\n"
            "Barcha boshqa endpointlardan foydalanish uchun avval **Login** qiling "
            "va olingan `access_token` ni `Authorize 🔒` tugmasi orqali kiriting."
        ),
    },
    {
        "name": "📦 Mahsulotlar",
        "description": (
            "Kiyim-kechak **mahsulotlar katalogi** boshqaruvi.\n\n"
            "- Yangi kiyim qo'shish → ombor qoldig'i avtomatik yaratiladi\n"
            "- **Shtrix-kod** bo'yicha tezkor qidiruv (kassir uchun)\n"
            "- Narx, rang, razmer tahrirlash\n"
            "- Mahsulotni yashirish *(soft delete)*\n\n"
            "**Kim bajara oladi:** Admin, Omborchi (qo'shish/tahrirlash) | Kassir (ko'rish/qidiruv)"
        ),
    },
    {
        "name": "🏭 Ombor",
        "description": (
            "**Ombor qoldiqlari** boshqaruvi.\n\n"
            "- Barcha tovarlar qoldig'ini ko'rish\n"
            "- Yangi tovar kirim qilish *(qoldiq oshirish)*\n"
            "- **Ogohlantirish:** kam qolgan tovarlar ro'yxati *(default: 5 donadan kam)*\n\n"
            "**Kim bajara oladi:** Admin, Omborchi (kirim) | Hammasi (ko'rish)"
        ),
    },
    {
        "name": "👤 Mijozlar",
        "description": (
            "Do'kon **mijozlari** ro'yxati va boshqaruvi.\n\n"
            "- Jismoniy va yuridik shaxslar *(STIR/INN bilan)*\n"
            "- Telefon raqami bo'yicha qidiruv\n"
            "- Mijoz ma'lumotlarini tahrirlash\n\n"
            "**Kim bajara oladi:** Admin, Kassir"
        ),
    },
    {
        "name": "🧾 Hisob-Fakturalar",
        "description": (
            "**Elektron Hisob-Faktura** yaratish va boshqarish.\n\n"
            "### Sotuv qilish:\n"
            "1. `POST /invoices/` → Mijoz va mahsulotlar ro'yxatini yuboring\n"
            "2. Tizim avtomatik: ombor tekshiradi → miqdor ayiradi → faktura raqami beradi\n"
            "3. Omborda yetarli bo'lmasa → **400 xatosi** (hech narsa o'zgarmaydi)\n\n"
            "### Fakturani bekor qilish:\n"
            "`PUT /invoices/{id}/cancel` → Barcha mahsulotlar omborga **qaytariladi**\n\n"
            "**Kim bajara oladi:** Admin, Kassir"
        ),
    },
    {
        "name": "Asosiy",
        "description": "API holati va tizim ma'lumotlari.",
    },
    {
        "name": "Tizim",
        "description": "Server va ma'lumotlar bazasi holati tekshiruvi *(Health Check)*.",
    },
]

app = FastAPI(
    title="🛍️ Elektron Hisob-Faktura Tizimi",
    version=settings.APP_VERSION,
    description="""
## Kiyim-kechak do'koni uchun professional E-Faktura tizimi

Bu API orqali do'koningizning barcha sotuv jarayonlarini boshqarishingiz mumkin.

---

### 🚀 Tez boshlash:

1. **Login qiling** → `/api/v1/auth/login` endpointida `admin` / `Admin@12345`
2. Olingan **`access_token`** ni yuqoridagi `Authorize 🔒` tugmasiga kiriting
3. Endi barcha endpointlar faol!

---

### 👥 Rollar va huquqlar:

| Rol | Huquqlar |
|-----|----------|
| 🔴 **Admin** | Barcha amallar: xodim qo'shish, o'chirish, faktura bekor qilish |
| 🟡 **Kassir** | Mijoz qo'shish, faktura yaratish, mahsulot ko'rish |
| 🟢 **Omborchi** | Mahsulot qo'shish/tahrirlash, kirim qilish |

---

### 📊 Tizim imkoniyatlari:

- ✅ JWT autentifikatsiya (Bearer token)
- ✅ Rol asosida kirish nazorati (RBAC)
- ✅ Atomik sotuv tranzaksiyasi (race condition himoyasi)
- ✅ Ombor avtomatik nazorati
- ✅ Faktura bekor qilishda ombor tiklanishi
- ✅ Shtrix-kod bo'yicha tezkor qidiruv
    """,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    contact={
        "name": "E-Faktura Tizimi",
        "email": "support@efaktura.uz",
    },
    license_info={
        "name": "MIT License",
    },
)


# ============================================================
# CORS (Cross-Origin Resource Sharing) o'rnatish
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,  # config.py'dan ro'yxat olinadi
    allow_credentials=True,
    allow_methods=["*"],   # Barcha HTTP metodlarga ruxsat
    allow_headers=["*"],   # Barcha headerlarga ruxsat
)


# ============================================================
# API Router'larni ulash
# ============================================================
app.include_router(auth_router.router,      prefix="/api/v1")
app.include_router(products_router.router,  prefix="/api/v1")
app.include_router(inventory_router.router, prefix="/api/v1")
app.include_router(customers_router.router, prefix="/api/v1")
app.include_router(invoices_router.router,  prefix="/api/v1")


# ============================================================
# Frontend fayllarini ulash (Static Files)
# ============================================================
import os
if os.path.isdir("frontend"):
    app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")
    


# ============================================================
# Asosiy yo'nalishlar (Routes)
# ============================================================

@app.get("/", tags=["Asosiy"])
async def root():
    """
    Ilovaning bosh sahifasi.
    API ishlayotganini tasdiqlash uchun sodda javob qaytaradi.
    """
    return JSONResponse(
        content={
            "success": True,
            "message": f"✅ {settings.APP_NAME} API muvaffaqiyatli ishlayapti!",
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "redoc": "/redoc",
        }
    )


@app.get("/health", tags=["Tizim"])
async def health_check():
    """
    Tizim holati tekshiruvi (Health Check).
    Render.com va monitoring tizimlari ushbu endpoint'ni ishlatadi.
    """
    db_status = check_database_connection()

    response_data = {
        "success": db_status["status"] == "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db_status,
    }

    # Baza bilan ulanib bo'lmasa, 503 qaytarish
    status_code = 200 if db_status["status"] == "ok" else 503
    return JSONResponse(content=response_data, status_code=status_code)


# ============================================================
# Endpoint xaritasi (umumiy ko'rinish)
# ============================================================
# GET  /                      → API ishlayotganini tasdiqlash
# GET  /health                → Tizim va baza holati
# GET  /docs                  → Swagger UI
# GET  /redoc                 → ReDoc
#
# POST /api/v1/auth/register  → Yangi xodim (faqat admin)
# POST /api/v1/auth/login     → JWT token olish
# GET  /api/v1/auth/me        → Joriy foydalanuvchi profili
# POST /api/v1/auth/logout    → Tizimdan chiqish
#
# [4-QADAM] GET/POST /api/v1/products  → Mahsulotlar CRUD
# [4-QADAM] GET/POST /api/v1/invoices  → Fakturalar CRUD
# [4-QADAM] GET/POST /api/v1/customers → Mijozlar CRUD
# [4-QADAM] GET/POST /api/v1/inventory → Ombor CRUD
