"""
app/schemas/all_schemas.py
===========================
E-Faktura tizimi uchun barcha Pydantic sxemalari.

Har bir model uchun uch xil sxema:
    XxxBase    → Umumiy maydonlar (meros olish uchun asos)
    XxxCreate  → Yaratish uchun (POST so'rovlarda keladi, parol ochiq holda)
    XxxUpdate  → Yangilash uchun (PATCH so'rovlarda, barcha maydonlar ixtiyoriy)
    XxxResponse → Javobda qaytariladigan ma'lumot (parol_hash YO'Q)

Nima uchun alohida?
    - CREATE → foydalanuvchi yuboradi (parol ochiq matn)
    - RESPONSE → biz qaytaramiz (parol_hash hech qachon qaytarilmaydi)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator, model_validator

# Modellardan enum turlarini import qilish (bir joyda saqlash uchun)
from app.models.all_models import UserRole, CustomerType, InvoiceStatus


# ============================================================
#  YORDAMCHI KLASS — ORM modellaridan o'qish uchun
# ============================================================

class OrmBase(BaseModel):
    """
    Barcha 'Response' sxemalari shu klassdan meros oladi.
    `model_config` SQLAlchemy ORM obyektlarini Pydantic'ga o'giradi.
    """
    model_config = {"from_attributes": True}


# ============================================================
#  1. FOYDALANUVCHI SXEMALARI (User Schemas)
# ============================================================

class UserBase(BaseModel):
    """Foydalanuvchining umumiy maydonlari."""
    ism_sharif : str       = Field(..., min_length=3, max_length=150,
                                   examples=["Alisher Karimov"],
                                   description="To'liq ism-sharif")
    login      : str       = Field(..., min_length=4, max_length=100,
                                   examples=["alisher_k"],
                                   description="Tizimga kirish logini (noyob)")
    rol        : UserRole  = Field(default=UserRole.kassir,
                                   description="Foydalanuvchi roli")

    @field_validator("login")
    @classmethod
    def login_faqat_lotincha(cls, v: str) -> str:
        """Login faqat lotin harflari, raqamlar va '_' belgisidan iborat bo'lishi kerak."""
        if not v.replace("_", "").replace(".", "").isalnum():
            raise ValueError("Login faqat lotin harflari, raqamlar va '_' belgisidan iborat bo'lishi kerak.")
        return v.lower()


class UserCreate(UserBase):
    """Yangi foydalanuvchi yaratish uchun (POST /users)."""
    parol : str = Field(..., min_length=6, max_length=100,
                        examples=["Xavfsiz@2024"],
                        description="Kamida 6 ta belgi bo'lsin")


class UserUpdate(BaseModel):
    """Foydalanuvchini yangilash uchun (PATCH /users/{id}). Barcha maydonlar ixtiyoriy."""
    ism_sharif  : Optional[str]      = Field(None, min_length=3, max_length=150)
    rol         : Optional[UserRole] = None
    is_active   : Optional[bool]     = None
    parol       : Optional[str]      = Field(None, min_length=6, max_length=100)


class UserResponse(OrmBase):
    """API javobida qaytariladigan foydalanuvchi ma'lumotlari. PAROL qaytarilmaydi!"""
    id          : int
    ism_sharif  : str
    login       : str
    rol         : UserRole
    is_active   : bool
    yaratilgan  : datetime


# ============================================================
#  2. MAHSULOT SXEMALARI (Product Schemas)
# ============================================================

class ProductBase(BaseModel):
    """Mahsulotning umumiy maydonlari."""
    kiyim_nomi     : str            = Field(..., min_length=2, max_length=200,
                                            examples=["Erkaklar ko'ylagi"])
    shtrix_kod     : str            = Field(..., min_length=4, max_length=50,
                                            examples=["4600123456789"])
    razmer         : Optional[str]  = Field(None, max_length=10, examples=["L"])
    rang           : Optional[str]  = Field(None, max_length=50, examples=["Ko'k"])
    kelgan_narxi   : float          = Field(..., ge=0, examples=[85000.0],
                                            description="Yetkazib beruvchidan kelgan narxi")
    sotilish_narxi : float          = Field(..., ge=0, examples=[130000.0],
                                            description="Mijozga sotiladigan narxi")
    tavsif         : Optional[str]  = Field(None, max_length=1000)

    @model_validator(mode="after")
    def sotish_narxi_katta_bolsin(self) -> "ProductBase":
        """Sotilish narxi kelgan narxdan kichik bo'lmasligi kerak."""
        if self.sotilish_narxi < self.kelgan_narxi:
            raise ValueError(
                f"Sotilish narxi ({self.sotilish_narxi}) kelgan narxdan "
                f"({self.kelgan_narxi}) kichik bo'lishi mumkin emas!"
            )
        return self


class ProductCreate(ProductBase):
    """Yangi mahsulot yaratish uchun (POST /products)."""
    boshlangich_miqdor: int = Field(default=0, ge=0,
                                    description="Ombordagi boshlang'ich qoldiq miqdori")


class ProductUpdate(BaseModel):
    """Mahsulotni yangilash uchun (PATCH /products/{id}). Barcha maydonlar ixtiyoriy."""
    kiyim_nomi     : Optional[str]   = Field(None, min_length=2, max_length=200)
    razmer         : Optional[str]   = Field(None, max_length=10)
    rang           : Optional[str]   = Field(None, max_length=50)
    kelgan_narxi   : Optional[float] = Field(None, ge=0)
    sotilish_narxi : Optional[float] = Field(None, ge=0)
    tavsif         : Optional[str]   = None
    is_active      : Optional[bool]  = None


class ProductResponse(OrmBase):
    """API javobida qaytariladigan mahsulot ma'lumotlari."""
    id             : int
    kiyim_nomi     : str
    shtrix_kod     : str
    razmer         : Optional[str]
    rang           : Optional[str]
    kelgan_narxi   : float
    sotilish_narxi : float
    tavsif         : Optional[str]
    is_active      : bool
    yaratilgan     : datetime


# ============================================================
#  3. OMBOR SXEMALARI (Inventory Schemas)
# ============================================================

class InventoryBase(BaseModel):
    """Ombor asosiy ma'lumotlari."""
    miqdor : int = Field(..., ge=0, description="Ombordagi qoldiq (musbat son)")


class InventoryUpdate(BaseModel):
    """Ombor qoldig'ini yangilash uchun."""
    miqdor: int = Field(..., ge=0)


class InventoryResponse(OrmBase):
    """API javobida qaytariladigan ombor ma'lumotlari."""
    id                 : int
    product_id         : int
    miqdor             : int
    oxirgi_yangilanish : datetime

    # Bog'liq mahsulot ma'lumotlarini ham qaytarish
    product : Optional[ProductResponse] = None


# ============================================================
#  4. MIJOZ SXEMALARI (Customer Schemas)
# ============================================================

class CustomerBase(BaseModel):
    """Mijozning umumiy maydonlari."""
    ism_sharif  : str          = Field(..., min_length=2, max_length=200,
                                       examples=["Shodmon Toshmatov"])
    telefon     : str          = Field(..., max_length=20,
                                       examples=["+998901234567"])
    mijoz_turi  : CustomerType = Field(default=CustomerType.jismoniy)
    stir_inn    : Optional[str] = Field(None, max_length=20,
                                        description="Yuridik shaxslar uchun STIR/INN")
    manzil      : Optional[str] = Field(None, max_length=300)

    @field_validator("telefon")
    @classmethod
    def telefon_formati(cls, v: str) -> str:
        """Telefon raqami + belgisi bilan boshlanishi va faqat raqamlardan iborrat bo'lishi kerak."""
        cleaned = v.replace(" ", "").replace("-", "")
        if not cleaned.startswith("+") or not cleaned[1:].isdigit():
            raise ValueError("Telefon raqami '+' bilan boshlanib, faqat raqamlardan iborat bo'lishi kerak (+998901234567)")
        if len(cleaned) < 10 or len(cleaned) > 16:
            raise ValueError("Telefon raqami uzunligi 10–16 ta belgi bo'lishi kerak.")
        return cleaned

    @model_validator(mode="after")
    def yuridik_stir_tekshir(self) -> "CustomerBase":
        """Yuridik shaxs uchun STIR/INN majburiy bo'lmasa ham, agar berilsa tekshirish."""
        if self.mijoz_turi == CustomerType.yuridik and self.stir_inn:
            if not self.stir_inn.isdigit():
                raise ValueError("STIR/INN faqat raqamlardan iborat bo'lishi kerak.")
        return self


class CustomerCreate(CustomerBase):
    """Yangi mijoz yaratish uchun (POST /customers)."""
    pass


class CustomerUpdate(BaseModel):
    """Mijozni yangilash uchun (PATCH /customers/{id}). Barcha maydonlar ixtiyoriy."""
    ism_sharif  : Optional[str]          = Field(None, min_length=2, max_length=200)
    telefon     : Optional[str]          = Field(None, max_length=20)
    mijoz_turi  : Optional[CustomerType] = None
    stir_inn    : Optional[str]          = Field(None, max_length=20)
    manzil      : Optional[str]          = Field(None, max_length=300)


class CustomerResponse(OrmBase):
    """API javobida qaytariladigan mijoz ma'lumotlari."""
    id          : int
    ism_sharif  : str
    telefon     : str
    mijoz_turi  : CustomerType
    stir_inn    : Optional[str]
    manzil      : Optional[str]
    yaratilgan  : datetime


# ============================================================
#  5. FAKTURA TAFSILOTI SXEMALARI (InvoiceItem Schemas)
# ============================================================

class InvoiceItemBase(BaseModel):
    """Faktura qatori asosiy maydonlari."""
    product_id  : int   = Field(..., gt=0, description="Mahsulot ID si")
    miqdor      : int   = Field(..., gt=0, description="Sotilgan miqdor (kamida 1)")


class InvoiceItemCreate(InvoiceItemBase):
    """
    Faktura yaratishda yuboriladi.
    `kiyim_narxi` va `jami` server tomonidan avtomatik hisoblanadi,
    shuning uchun bu yerda YO'Q — narxni aldash mumkin emas.
    """
    pass


class InvoiceItemResponse(OrmBase):
    """API javobida qaytariladigan faktura qatori."""
    id          : int
    invoice_id  : int
    product_id  : int
    miqdor      : int
    kiyim_narxi : float   # Sotilgan vaqtdagi narx (tarixiy ma'lumot)
    jami        : float   # miqdor × kiyim_narxi

    # Mahsulot haqida qisqacha ma'lumot (optional nested)
    product : Optional[ProductResponse] = None


# ============================================================
#  6. FAKTURA SXEMALARI (Invoice Schemas)
# ============================================================

class InvoiceBase(BaseModel):
    """Fakturaning umumiy maydonlari."""
    customer_id : int              = Field(..., gt=0, description="Mijoz ID si")
    izoh        : Optional[str]    = Field(None, max_length=1000)


class InvoiceCreate(InvoiceBase):
    """
    Yangi faktura yaratish uchun (POST /invoices).

    Muhim:
        - `faktura_raqami` server tomonidan avtomatik generatsiya qilinadi
        - `user_id` JWT tokendan olinadi (kim login qilgan bo'lsa)
        - `umumiy_summa` InvoiceItem'lar asosida server hisoblaydi
        - `items` kamida BITTA qatorni o'z ichiga olishi kerak
    """
    items : List[InvoiceItemCreate] = Field(..., min_length=1,
                                            description="Faktura qatorlari (kamida 1 ta)")


class InvoiceUpdate(BaseModel):
    """Fakturani yangilash uchun (PATCH /invoices/{id}). Faqat status va izohni o'zgartirish mumkin."""
    status  : Optional[InvoiceStatus] = None
    izoh    : Optional[str]           = Field(None, max_length=1000)


class InvoiceResponse(OrmBase):
    """
    API javobida qaytariladigan to'liq faktura ma'lumotlari.
    Mijoz, xodim va barcha qatorlarni o'z ichiga oladi (nested response).
    """
    id              : int
    faktura_raqami  : str
    customer_id     : int
    user_id         : int
    umumiy_summa    : float
    status          : InvoiceStatus
    izoh            : Optional[str]
    yaratilgan_sana : datetime

    # Bog'liq obyektlar (nested)
    mijoz  : Optional[CustomerResponse]       = None
    xodim  : Optional[UserResponse]           = None
    items  : List[InvoiceItemResponse]        = []


class InvoiceListResponse(OrmBase):
    """Fakturalar ro'yxatini qaytarish uchun (qisqacha ko'rinish)."""
    id              : int
    faktura_raqami  : str
    umumiy_summa    : float
    status          : InvoiceStatus
    yaratilgan_sana : datetime
    mijoz           : Optional[CustomerResponse] = None


# ============================================================
#  UMUMIY JAVOB SXEMALARI
# ============================================================

class MessageResponse(BaseModel):
    """Muvaffaqiyat/xato xabarlar uchun umumiy javob sxemasi."""
    success : bool   = True
    message : str
    data    : Optional[dict] = None


class PaginatedResponse(BaseModel):
    """Sahifalash (pagination) uchun umumiy javob sxemasi."""
    total   : int = Field(description="Umumiy yozuvlar soni")
    page    : int = Field(description="Joriy sahifa raqami")
    size    : int = Field(description="Har bir sahifadagi yozuvlar soni")
    pages   : int = Field(description="Umumiy sahifalar soni")


# ============================================================
#  4-QADAM UCHUN QO'SHIMCHA SXEMALAR
# ============================================================

class ProductWithStock(OrmBase):
    """
    Mahsulot ma'lumotlari + ombor qoldig'i birgalikda.
    Ro'yxat endpointida qulay ko'rinish uchun.
    """
    id             : int
    kiyim_nomi     : str
    shtrix_kod     : str
    razmer         : Optional[str]
    rang           : Optional[str]
    kelgan_narxi   : float
    sotilish_narxi : float
    tavsif         : Optional[str]
    is_active      : bool
    yaratilgan     : datetime
    # Ombor qoldig'i (inventory relationship'dan)
    ombor_miqdor   : Optional[int] = None   # Inventory.miqdor (computed)


class ProductListPaginated(BaseModel):
    """Mahsulotlar sahifalangan ro'yxati."""
    total   : int
    page    : int
    size    : int
    pages   : int
    items   : List[ProductResponse]


class InventoryListPaginated(BaseModel):
    """Ombor yozuvlari sahifalangan ro'yxati."""
    total   : int
    page    : int
    size    : int
    pages   : int
    items   : List[InventoryResponse]


class AddStockRequest(BaseModel):
    """
    Ombor kirim so'rovi — mavjud mahsulot miqdorini oshirish.
    Yangi mahsulot qo'shib bo'lmaydi, faqat qoldiqni ko'paytirish.
    """
    product_id : int = Field(..., gt=0,  description="Qaysi mahsulotni kirish qilmoqsiz")
    miqdor     : int = Field(..., gt=0,  description="Kirim miqdori (kamida 1 dona)",
                             examples=[50])
    izoh       : Optional[str] = Field(None, max_length=500,
                                       description="Kirim sababi yoki izoh (ixtiyoriy)",
                                       examples=["Yangi partiya keldi"])


class AddStockResponse(BaseModel):
    """Kirim amalga oshirilgandan keyin qaytariladigan javob."""
    success        : bool = True
    message        : str
    product_id     : int
    kiyim_nomi     : str
    kirim_miqdor   : int     # Kirim qilingan miqdor
    yangi_qoldiq   : int     # Kirimdan keyingi ombor qoldig'i
    eski_qoldiq    : int     # Kirimdan oldingi qoldiq


class LowStockResponse(BaseModel):
    """Omborda kam qolgan mahsulot yozuvi."""
    product_id     : int
    kiyim_nomi     : str
    shtrix_kod     : str
    razmer         : Optional[str]
    rang           : Optional[str]
    mavjud_miqdor  : int
    chegarа        : int     # Ogohlantirish chegarasi


class LowStockListResponse(BaseModel):
    """Omborda kam qolgan mahsulotlar ro'yxati."""
    chegara        : int     # Qaysi chegara ishlatildi
    jami_soni      : int     # Nechta mahsulot kam qolgan
    items          : List[LowStockResponse]

