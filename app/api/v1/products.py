"""
app/api/v1/products.py
=======================
Mahsulotlar (Kiyimlar) boshqaruvi uchun API Router.

Endpoint'lar:
    POST /api/v1/products/          → Yangi kiyim qo'shish (admin/omborchi)
    GET  /api/v1/products/          → Barcha kiyimlar (sahifalab, filtrlab)
    GET  /api/v1/products/search    → Shtrix-kod bo'yicha qidirish (kassir uchun)
    GET  /api/v1/products/{id}      → Bitta mahsulot tafsiloti
    PUT  /api/v1/products/{id}      → Mahsulot ma'lumotlarini yangilash (admin/omborchi)
    DELETE /api/v1/products/{id}    → Mahsulotni o'chirish (faqat admin, soft delete)

Arxitektura qarorlari:
    - Kiyim qo'shilganda Inventory yozuvi AVTOMATIK yaratiladi (atomik tranzaksiya)
    - Soft delete: is_active=False (ma'lumot yo'qolmaydi, tarixi saqlanadi)
    - shtrix_kod ustunida INDEX bor → qidiruv O(log n) tezlikda
    - Barcha o'zgarishlar tranzaksiya ichida — ya hamma o'zgaradi, ya hech nima
"""

import logging
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.all_models import Product, Inventory, User
from app.schemas.all_schemas import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductListPaginated,
    MessageResponse,
)
from app.api.deps import (
    get_current_user,
    get_omborchi_or_admin,
    get_admin_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["📦 Mahsulotlar"])


# ============================================================
#  1. YANGI KIYIM QO'SHISH  (POST /products/)
# ============================================================

@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yangi kiyim qo'shish",
    description=(
        "Katalogga yangi kiyim qo'shadi. Mahsulot qo'shilishi bilan "
        "`inventory` jadvalida ham qoldig'i avtomatik yaratiladi. "
        "**Faqat admin va omborchi** bajara oladi."
    ),
)
def create_product(
    product_data : ProductCreate,
    db           : Session = Depends(get_db),
    current_user : User    = Depends(get_omborchi_or_admin),
) -> ProductResponse:
    """
    Yangi mahsulot yaratish (Inventory bilan birga atomik tranzaksiya).

    Xatoliklar:
        400 → Bunday shtrix-kod allaqachon mavjud
        403 → Ruxsat yo'q (faqat admin/omborchi)
        422 → Validatsiya xatosi (narx, razmer va hokazo)
    """
    # ── 1. Shtrix-kod noyobligini tekshirish ───────────────────
    existing = db.query(Product).filter(
        Product.shtrix_kod == product_data.shtrix_kod
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{product_data.shtrix_kod}' shtrix-kodli mahsulot allaqachon mavjud. "
                f"(ID: {existing.id}, Nom: '{existing.kiyim_nomi}')"
            ),
        )

    # ── 2. Mahsulot va Inventory birgalikda yaratish ──────────
    try:
        # 2a. Mahsulotni yaratish
        new_product = Product(
            kiyim_nomi     = product_data.kiyim_nomi,
            shtrix_kod     = product_data.shtrix_kod,
            razmer         = product_data.razmer,
            rang           = product_data.rang,
            kelgan_narxi   = product_data.kelgan_narxi,
            sotilish_narxi = product_data.sotilish_narxi,
            tavsif         = product_data.tavsif,
            is_active      = True,
        )
        db.add(new_product)
        db.flush()   # ID generatsiya qilish (commit qilmasdan)

        # 2b. Inventory yozuvini avtomatik yaratish
        inventory = Inventory(
            product_id = new_product.id,
            miqdor     = product_data.boshlangich_miqdor,
        )
        db.add(inventory)

        # 2c. Hamma birga commit qilish (atomik)
        db.commit()
        db.refresh(new_product)

    except IntegrityError as e:
        db.rollback()
        logger.error(f"❌ Mahsulot yaratishda IntegrityError: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mahsulot yaratishda xatolik. Shtrix-kod noyob bo'lishi kerak.",
        )

    logger.info(
        f"✅ Yangi mahsulot: '{new_product.kiyim_nomi}' "
        f"(ID={new_product.id}, qoldiq={inventory.miqdor}) "
        f"| Xodim: '{current_user.login}'"
    )
    return ProductResponse.model_validate(new_product)


# ============================================================
#  2. MAHSULOTLAR RO'YXATI  (GET /products/)
# ============================================================

@router.get(
    "/",
    response_model=ProductListPaginated,
    summary="Barcha kiyimlar ro'yxati",
    description=(
        "Kiyimlar katalogini sahifalab qaytaradi. "
        "Nom, razmer va rang bo'yicha filtrlash mumkin. "
        "Barcha autentifikatsiya qilingan foydalanuvchilar ko'ra oladi."
    ),
)
def list_products(
    page          : int            = Query(default=1,   ge=1,    description="Sahifa raqami (1 dan boshlaydi)"),
    size          : int            = Query(default=20,  ge=1, le=100, description="Sahifadagi yozuvlar soni"),
    kiyim_nomi    : Optional[str]  = Query(default=None, description="Nom bo'yicha qidirish (qisman moslik)"),
    razmer        : Optional[str]  = Query(default=None, description="Razmer bo'yicha filtrlash (S, M, L, ...)"),
    rang          : Optional[str]  = Query(default=None, description="Rang bo'yicha filtrlash"),
    faqat_faol    : bool           = Query(default=True, description="Faqat faol mahsulotlarni ko'rsatish"),
    db            : Session        = Depends(get_db),
    _             : User           = Depends(get_current_user),   # Faqat login qilganlar
) -> ProductListPaginated:
    """
    Mahsulotlar sahifalangan ro'yxati.

    Filtr parametrlari kombinatsiyalanishi mumkin:
        GET /products/?razmer=L&rang=qora&page=2&size=10
    """
    # ── So'rovni qurish (query building) ──────────────────────
    query = db.query(Product)

    if faqat_faol:
        query = query.filter(Product.is_active == True)  # noqa: E712

    if kiyim_nomi:
        # ILIKE — katta-kichik harfga sezgir emas (PostgreSQL)
        query = query.filter(
            Product.kiyim_nomi.ilike(f"%{kiyim_nomi}%")
        )

    if razmer:
        query = query.filter(Product.razmer == razmer)

    if rang:
        query = query.filter(Product.rang.ilike(f"%{rang}%"))

    # ── Umumiy soni hisoblash (sahifalash uchun) ────────────
    total = query.count()
    total_pages = math.ceil(total / size) if total > 0 else 1

    # ── Sahifalash: OFFSET va LIMIT ─────────────────────────
    offset = (page - 1) * size
    products = (
        query
        .order_by(Product.id.desc())   # Eng yangi mahsulotlar birinchi
        .offset(offset)
        .limit(size)
        .all()
    )

    return ProductListPaginated(
        total = total,
        page  = page,
        size  = size,
        pages = total_pages,
        items = [ProductResponse.model_validate(p) for p in products],
    )


# ============================================================
#  3. SHTRIX-KOD BO'YICHA QIDIRISH  (GET /products/search)
# ============================================================

@router.get(
    "/search",
    response_model=ProductResponse,
    summary="Shtrix-kod bo'yicha qidirish (Kassir uchun)",
    description=(
        "Kiyimni shtrix-kodi bo'yicha **aniq va tezkor** qidiradi. "
        "Kassir skaner bilan o'qitganda shu endpoint ishlatiladi. "
        "`shtrix_kod` ustunida INDEX bor — O(log n) tezlikda ishlaydi."
    ),
)
def search_by_barcode(
    shtrix_kod : str     = Query(..., min_length=4, description="Shtrix-kod (skanerlanganda)",
                                 examples=["4600123456789"]),
    db         : Session = Depends(get_db),
    _          : User    = Depends(get_current_user),   # Kassir ham kirishi mumkin
) -> ProductResponse:
    """
    Shtrix-kod indeksi orqali bir zumda mahsulot topiladi.

    Xatoliklar:
        404 → Bunday shtrix-kodli mahsulot topilmadi
        404 → Mahsulot mavjud lekin faol emas (o'chirilgan)
    """
    product = db.query(Product).filter(
        Product.shtrix_kod == shtrix_kod.strip()
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{shtrix_kod}' shtrix-kodli mahsulot topilmadi.",
        )

    if not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{shtrix_kod}' shtrix-kodli mahsulot katalogdan o'chirilgan.",
        )

    return ProductResponse.model_validate(product)


# ============================================================
#  4. BITTA MAHSULOT TAFSILOTI  (GET /products/{id})
# ============================================================

@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Mahsulot tafsiloti (ID bo'yicha)",
)
def get_product(
    product_id : int,
    db         : Session = Depends(get_db),
    _          : User    = Depends(get_current_user),
) -> ProductResponse:
    """Mahsulot ID si bo'yicha to'liq ma'lumot."""
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ID={product_id} bo'lgan mahsulot topilmadi.",
        )

    return ProductResponse.model_validate(product)


# ============================================================
#  5. MAHSULOTNI YANGILASH  (PUT /products/{id})
# ============================================================

@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Mahsulot ma'lumotlarini yangilash",
    description=(
        "Kiyim narxi, rangi, razmeri yoki boshqa ma'lumotlarini yangilaydi. "
        "**Faqat admin va omborchi** bajara oladi. "
        "Shtrix-kodni o'zgartirish mumkin emas (o'chirish kerak)."
    ),
)
def update_product(
    product_id   : int,
    product_data : ProductUpdate,
    db           : Session = Depends(get_db),
    current_user : User    = Depends(get_omborchi_or_admin),
) -> ProductResponse:
    """
    Mahsulot ma'lumotlarini qisman yangilash (PATCH mantiqida ishlaydi).
    Faqat yuborilgan maydonlar o'zgartiriladi — qolganlar o'zgarmaydi.

    Xatoliklar:
        404 → Mahsulot topilmadi
        400 → Sotish narxi kelgan narxdan kichik
        403 → Ruxsat yo'q
    """
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ID={product_id} bo'lgan mahsulot topilmadi.",
        )

    # ── Faqat yuborilgan maydonlarni yangilash ────────────────
    update_fields = product_data.model_dump(exclude_unset=True)

    # Narx mantiqini tekshirish: agar ikkala narx ham yangilanayotgan bo'lsa
    yangi_kelgan  = update_fields.get("kelgan_narxi",   product.kelgan_narxi)
    yangi_sotish  = update_fields.get("sotilish_narxi", product.sotilish_narxi)
    if yangi_sotish < yangi_kelgan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Sotilish narxi ({yangi_sotish}) kelgan narxdan "
                f"({yangi_kelgan}) kichik bo'lishi mumkin emas!"
            ),
        )

    # Maydonlarni bazada yangilash
    for field, value in update_fields.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    logger.info(
        f"✏️ Mahsulot yangilandi: ID={product_id}, "
        f"o'zgartirilgan={list(update_fields.keys())} "
        f"| Xodim: '{current_user.login}'"
    )
    return ProductResponse.model_validate(product)


# ============================================================
#  6. MAHSULOTNI O'CHIRISH  (DELETE /products/{id}) — Soft Delete
# ============================================================

@router.delete(
    "/{product_id}",
    response_model=MessageResponse,
    summary="Mahsulotni o'chirish (Soft delete, faqat Admin)",
    description=(
        "Mahsulotni katalogdan yashiradi (`is_active=False`). "
        "Ma'lumot bazadan o'chirilmaydi — faktura tarixi saqlanib qoladi. "
        "**Faqat admin** bajara oladi."
    ),
)
def delete_product(
    product_id   : int,
    db           : Session = Depends(get_db),
    current_user : User    = Depends(get_admin_user),   # Faqat admin!
) -> MessageResponse:
    """
    Mahsulotni soft delete qilish.

    Nima uchun hard delete emas?
        - Faktura tafsilotlari (InvoiceItem) mahsulotga murojaat qiladi
        - O'chirilsa, tarixiy fakturalar buzilishi mumkin
        - is_active=False → katalogdan yashiriladi, tarix saqlanadi
    """
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ID={product_id} bo'lgan mahsulot topilmadi.",
        )

    if not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{product.kiyim_nomi}' (ID={product_id}) allaqachon o'chirilgan.",
        )

    product.is_active = False
    db.commit()

    logger.info(
        f"🗑️ Mahsulot o'chirildi (soft): '{product.kiyim_nomi}' ID={product_id} "
        f"| Admin: '{current_user.login}'"
    )
    return MessageResponse(
        success=True,
        message=f"'{product.kiyim_nomi}' katalogdan muvaffaqiyatli yashirildi.",
    )
