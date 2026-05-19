"""
app/models/all_models.py
=========================
Kiyim-kechak do'koni E-Faktura tizimi uchun barcha SQLAlchemy ORM modellari.

Jadvallar va ularning aloqalari:
    User  ──────────────────────────── Invoice  (bir xodim ko'p faktura yozadi)
    Customer ───────────────────────── Invoice  (bir mijozga ko'p faktura)
    Invoice ────────────────────────── InvoiceItem (bir fakturada ko'p qator)
    Product ────────────────────────── InvoiceItem (bir mahsulot ko'p faktura qatorida)
    Product ────────────────────────── Inventory (bir mahsulotning bir ombor qoldig'i)
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


# ============================================================
#  ENUM TURLARI — Ma'lumotlar bazasida saqlash uchun
# ============================================================

class UserRole(str, enum.Enum):
    """Foydalanuvchi rollari."""
    admin    = "admin"       # Barcha huquqlarga ega
    kassir   = "kassir"      # Faktura yozadi, mijozlar bilan ishlaydi
    omborchi = "omborchi"    # Ombor qoldiqlarini boshqaradi


class CustomerType(str, enum.Enum):
    """Mijoz turlari."""
    jismoniy = "jismoniy"  # Jismoniy shaxs (oddiy xaridor)
    yuridik  = "yuridik"   # Yuridik shaxs (korxona, STIR bilan)


class InvoiceStatus(str, enum.Enum):
    """Faktura holati."""
    kutilmoqda       = "kutilmoqda"       # To'lov kutilayotgan
    tolangan         = "tolangan"         # To'lov amalga oshirilgan
    bekor_qilingan   = "bekor_qilingan"   # Faktura bekor qilingan


# ============================================================
#  1. FOYDALANUVCHILAR JADVALI (users)
# ============================================================

class User(Base):
    """
    Tizim foydalanuvchilari: admin, kassir, omborchi.
    Har bir faktura qaysi xodim tomonidan yozilganini kuzatadi.
    """
    __tablename__ = "users"

    id          = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ism_sharif  = Column(String(150), nullable=False, comment="To'liq ism-sharif")
    login       = Column(String(100), unique=True, nullable=False, index=True,
                         comment="Tizimga kirish uchun noyob login")
    parol_hash  = Column(String(255), nullable=False,
                         comment="Bcrypt bilan xeshlangan parol")
    rol         = Column(
                     SAEnum(UserRole, name="user_role_enum"),
                     nullable=False,
                     default=UserRole.kassir,
                     comment="Foydalanuvchi roli: admin | kassir | omborchi"
                 )
    is_active   = Column(Boolean, default=True, nullable=False,
                         comment="Foydalanuvchi faol yoki o'chirilganmi")
    yaratilgan  = Column(DateTime(timezone=True), server_default=func.now(),
                         comment="Hisob yaratilgan sana")

    # ── Aloqalar ──────────────────────────────────────────────
    # Bir foydalanuvchi ko'p faktura yozishi mumkin
    invoices = relationship("Invoice", back_populates="xodim",
                            cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} login='{self.login}' rol='{self.rol}'>"


# ============================================================
#  2. MAHSULOTLAR JADVALI (products)
# ============================================================

class Product(Base):
    """
    Kiyim-kechak mahsulotlari katalogi.
    Har bir mahsulot razmer va rang bo'yicha alohida yozuv sifatida saqlanadi.
    """
    __tablename__ = "products"

    id              = Column(Integer, primary_key=True, index=True, autoincrement=True)
    kiyim_nomi      = Column(String(200), nullable=False, index=True,
                             comment="Mahsulot nomi (masalan: Ko'ylak, Shim)")
    shtrix_kod      = Column(String(50), unique=True, nullable=False, index=True,
                             comment="Shtrix-kod — noyob identifikator")
    razmer          = Column(String(10), nullable=True,
                             comment="Razmer: XS, S, M, L, XL, XXL yoki 36–54")
    rang            = Column(String(50), nullable=True,
                             comment="Rang nomi (masalan: qora, oq, ko'k)")
    kelgan_narxi    = Column(Float, nullable=False, default=0.0,
                             comment="Yetkazib beruvchidan kelgan narxi (so'm)")
    sotilish_narxi  = Column(Float, nullable=False, default=0.0,
                             comment="Mijozga sotiladigan narxi (so'm)")
    tavsif          = Column(Text, nullable=True,
                             comment="Mahsulot haqida qo'shimcha ma'lumot")
    is_active       = Column(Boolean, default=True, nullable=False,
                             comment="Mahsulot faol yoki katalogdan o'chirilganmi")
    yaratilgan      = Column(DateTime(timezone=True), server_default=func.now())
    yangilangan     = Column(DateTime(timezone=True), onupdate=func.now())

    # ── Aloqalar ──────────────────────────────────────────────
    # Mahsulotning ombordagi qoldig'i (bir-biriga)
    inventory = relationship("Inventory", back_populates="product",
                             uselist=False, cascade="all, delete-orphan")

    # Faktura tafsilotlarida ushbu mahsulotning yozuvlari
    invoice_items = relationship("InvoiceItem", back_populates="product")

    def __repr__(self) -> str:
        return (f"<Product id={self.id} nom='{self.kiyim_nomi}' "
                f"razmer='{self.razmer}' rang='{self.rang}'>")


# ============================================================
#  3. OMBOR JADVALI (inventory)
# ============================================================

class Inventory(Base):
    """
    Mahsulotlarning ombordagi qoldiqlari.
    Har bir mahsulot uchun BITTA yozuv mavjud (OneToOne).
    Kiyim sotilganda `miqdor` kamayadi, yangi kelganda ortadi.
    """
    __tablename__ = "inventory"

    id               = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id       = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"),
                              unique=True, nullable=False,
                              comment="Mahsulotga bog'langan kalit")
    miqdor           = Column(Integer, nullable=False, default=0,
                              comment="Hozirgi ombor qoldig'i (dona)")
    oxirgi_yangilanish = Column(
                          DateTime(timezone=True),
                          server_default=func.now(),
                          onupdate=func.now(),
                          comment="Qoldiq oxirgi yangilangan vaqt"
                        )

    # ── Aloqalar ──────────────────────────────────────────────
    product = relationship("Product", back_populates="inventory")

    def __repr__(self) -> str:
        return f"<Inventory product_id={self.product_id} miqdor={self.miqdor}>"


# ============================================================
#  4. MIJOZLAR JADVALI (customers)
# ============================================================

class Customer(Base):
    """
    Do'kon mijozlari: jismoniy va yuridik shaxslar.
    Yuridik shaxslar uchun STIR/INN majburiy emas, lekin ko'rsatilishi mumkin.
    """
    __tablename__ = "customers"

    # Bir mijozning bir xil telefon raqami bilan ikki marta kiritilmasligi uchun
    __table_args__ = (
        UniqueConstraint("telefon", name="uq_customer_telefon"),
    )

    id           = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ism_sharif   = Column(String(200), nullable=False,
                          comment="Jismoniy shaxs F.I.Sh. yoki korxona nomi")
    telefon      = Column(String(20), nullable=False, index=True,
                          comment="Telefon raqami (+998901234567 formatida)")
    stir_inn     = Column(String(20), nullable=True,
                          comment="Yuridik shaxs uchun STIR/INN raqami (ixtiyoriy)")
    mijoz_turi   = Column(
                     SAEnum(CustomerType, name="customer_type_enum"),
                     nullable=False,
                     default=CustomerType.jismoniy,
                     comment="Jismoniy yoki yuridik shaxs"
                  )
    manzil       = Column(String(300), nullable=True,
                          comment="Mijozning manzili (ixtiyoriy)")
    yaratilgan   = Column(DateTime(timezone=True), server_default=func.now())

    # ── Aloqalar ──────────────────────────────────────────────
    # Bir mijozga ko'p faktura yozilishi mumkin
    invoices = relationship("Invoice", back_populates="mijoz",
                            cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (f"<Customer id={self.id} ism='{self.ism_sharif}' "
                f"tur='{self.mijoz_turi}'>")


# ============================================================
#  5. FAKTURALAR JADVALI (invoices)
# ============================================================

class Invoice(Base):
    """
    Elektron hisob-fakturalar.
    Har bir faktura mijozga bog'langan va xodim tomonidan yozilgan.
    Faktura bir nechta mahsulot qatorlarini (InvoiceItem) o'z ichiga oladi.
    """
    __tablename__ = "invoices"

    id              = Column(Integer, primary_key=True, index=True, autoincrement=True)
    faktura_raqami  = Column(String(50), unique=True, nullable=False, index=True,
                             comment="Noyob faktura raqami (masalan: INV-2024-0001)")
    customer_id     = Column(Integer, ForeignKey("customers.id", ondelete="RESTRICT"),
                             nullable=False,
                             comment="Faktura kim nomiga: mijozlar jadvaliga FK")
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"),
                             nullable=False,
                             comment="Fakturani kim yozgan: foydalanuvchilar FK")
    umumiy_summa    = Column(Float, nullable=False, default=0.0,
                             comment="Barcha qatorlar summasi (so'm)")
    status          = Column(
                        SAEnum(InvoiceStatus, name="invoice_status_enum"),
                        nullable=False,
                        default=InvoiceStatus.kutilmoqda,
                        comment="To'lov holati"
                     )
    izoh            = Column(Text, nullable=True,
                             comment="Faktura bo'yicha qo'shimcha izoh")
    yaratilgan_sana = Column(DateTime(timezone=True), server_default=func.now(),
                             index=True, comment="Faktura yaratilgan sana va vaqt")
    yangilangan     = Column(DateTime(timezone=True), onupdate=func.now())

    # ── Aloqalar ──────────────────────────────────────────────
    # Faktura kimga yozilgan (mijoz)
    mijoz   = relationship("Customer", back_populates="invoices")

    # Fakturani kim yozgan (xodim)
    xodim   = relationship("User", back_populates="invoices")

    # Faktura ichidagi mahsulot qatorlari (one-to-many)
    # cascade="all, delete-orphan" → Faktura o'chirilsa, uning qatorlari ham o'chadi
    items   = relationship("InvoiceItem", back_populates="invoice",
                           cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (f"<Invoice id={self.id} raqam='{self.faktura_raqami}' "
                f"summa={self.umumiy_summa} status='{self.status}'>")


# ============================================================
#  6. FAKTURA TAFSILOTLARI JADVALI (invoice_items)
# ============================================================

class InvoiceItem(Base):
    """
    Faktura tafsilotlari — har bir fakturadagi alohida mahsulot qatorlari.

    Muhim: `kiyim_narxi` — sotilgan VAQTDAGI narx saqlanadi.
    Keyinchalik mahsulot narxi o'zgarsa ham, fakturadagi narx o'zgarishsiz qoladi.
    """
    __tablename__ = "invoice_items"

    id          = Column(Integer, primary_key=True, index=True, autoincrement=True)
    invoice_id  = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"),
                         nullable=False,
                         comment="Qaysi fakturaga tegishli")
    product_id  = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"),
                         nullable=False,
                         comment="Qaysi mahsulot sotilgan")
    miqdor      = Column(Integer, nullable=False, default=1,
                         comment="Sotilgan dona soni")
    kiyim_narxi = Column(Float, nullable=False,
                         comment="Sotilgan VAQTDAGI narx (narx o'zgarishidan himoya)")
    jami        = Column(Float, nullable=False, default=0.0,
                         comment="miqdor × kiyim_narxi = ushbu qator summasi")

    # ── Aloqalar ──────────────────────────────────────────────
    invoice = relationship("Invoice", back_populates="items")
    product = relationship("Product", back_populates="invoice_items")

    def __repr__(self) -> str:
        return (f"<InvoiceItem id={self.id} invoice_id={self.invoice_id} "
                f"product_id={self.product_id} miqdor={self.miqdor} jami={self.jami}>")
