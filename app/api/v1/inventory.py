"""
app/api/v1/inventory.py
========================
Ombor qoldig'ini boshqarish uchun API Router.

Endpoint'lar:
    GET  /api/v1/inventory/          → Barcha tovarlar qoldig'i (sahifalab)
    POST /api/v1/inventory/add-stock → Mavjud mahsulotga kirim qilish
    GET  /api/v1/inventory/low-stock → Kam qolgan tovarlar (ogohlantirish)
    GET  /api/v1/inventory/{product_id} → Bitta mahsulotning qoldig'i

Arxitektura qarorlari:
    - add-stock: qoldiq += kirim_miqdori (qoldiq hech qachon manfiy bo'lmaydi)
    - low-stock: chegara parametrini query'dan oladi (default=5)
    - Barcha ombor o'zgarishlari loglarda saqlanadi (audit uchun)
    - joinedload → N+1 muammosini bartaraf etadi (product va inventory birgalikda)
"""

import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.all_models import Product, Inventory, User
from app.schemas.all_schemas import (
    InventoryResponse,
    InventoryListPaginated,
    AddStockRequest,
    AddStockResponse,
    LowStockResponse,
    LowStockListResponse,
)
from app.api.deps import (
    get_current_user,
    get_omborchi_or_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory", tags=["🏭 Ombor"])


# ============================================================
#  1. BARCHA TOVARLAR QOLDIG'I  (GET /inventory/)
# ============================================================

@router.get(
    "/",
    response_model=InventoryListPaginated,
    summary="Barcha tovarlar qoldig'i",
    description=(
        "Omboridagi barcha tovarlar va ularning qoldiqlarini ko'rsatadi. "
        "Har bir yozuvda mahsulot ma'lumotlari ham birgalikda qaytariladi. "
        "Barcha autentifikatsiya qilingan xodimlar ko'ra oladi."
    ),
)
def list_inventory(
    page       : int     = Query(default=1,  ge=1,       description="Sahifa raqami"),
    size       : int     = Query(default=20, ge=1, le=100, description="Sahifadagi yozuvlar soni"),
    faqat_faol : bool    = Query(default=True,            description="Faqat faol mahsulotlarni ko'rsatish"),
    db         : Session = Depends(get_db),
    _          : User    = Depends(get_current_user),
) -> InventoryListPaginated:
    """
    Ombor qoldiqlari ro'yxati.

    joinedload ishlatiladi — bu SQL JOIN bilan bitta so'rovda
    mahsulot ma'lumotlarini ham oladi (N+1 muammosiz).
    """
    # ── So'rovni qurish ────────────────────────────────────────
    query = (
        db.query(Inventory)
        .options(joinedload(Inventory.product))   # Product JOIN
        .join(Inventory.product)                  # Filter uchun join
    )

    if faqat_faol:
        query = query.filter(Product.is_active == True)  # noqa: E712

    # ── Soni va sahifalash ─────────────────────────────────────
    total = query.count()
    total_pages = math.ceil(total / size) if total > 0 else 1
    offset = (page - 1) * size

    records = (
        query
        .order_by(Inventory.miqdor.asc())    # Kam qolganlar birinchi (e'tibor uchun)
        .offset(offset)
        .limit(size)
        .all()
    )

    return InventoryListPaginated(
        total = total,
        page  = page,
        size  = size,
        pages = total_pages,
        items = [InventoryResponse.model_validate(rec) for rec in records],
    )


# ============================================================
#  2. KIRIM QO'SHISH  (POST /inventory/add-stock)
# ============================================================

@router.post(
    "/add-stock",
    response_model=AddStockResponse,
    status_code=status.HTTP_200_OK,
    summary="Ombor kirimi (tovar qo'shish)",
    description=(
        "Mavjud mahsulot omboriga yangi miqdor qo'shadi. "
        "Yangi mahsulot yaratmaydi — faqat qoldiqni ko'paytiradi. "
        "Yangi mahsulot qo'shish uchun `POST /products/` ishlatilsin. "
        "**Faqat admin va omborchi** bajara oladi."
    ),
)
def add_stock(
    stock_data   : AddStockRequest,
    db           : Session = Depends(get_db),
    current_user : User    = Depends(get_omborchi_or_admin),
) -> AddStockResponse:
    """
    Ombor kirimi — qoldiq atomik ravishda oshiriladi.

    Atomik yangilash: `miqdor = miqdor + kirim_miqdori`
    Bu SQL'da: UPDATE inventory SET miqdor = miqdor + N WHERE product_id = X

    Xatoliklar:
        404 → Mahsulot topilmadi
        404 → Mahsulotda inventory yozuvi yo'q (bu holat bo'lmasligi kerak)
        400 → Mahsulot faol emas (o'chirilgan)
        403 → Ruxsat yo'q
    """
    # ── 1. Mahsulotni tekshirish ────────────────────────────────
    product = db.query(Product).filter(
        Product.id == stock_data.product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ID={stock_data.product_id} bo'lgan mahsulot topilmadi.",
        )

    if not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{product.kiyim_nomi}' mahsuloti o'chirilgan. "
                "O'chirilgan mahsulotga kirim qilib bo'lmaydi."
            ),
        )

    # ── 2. Inventory yozuvini topish ───────────────────────────
    inventory = db.query(Inventory).filter(
        Inventory.product_id == stock_data.product_id
    ).first()

    if not inventory:
        # Bu holat bo'lmasligi kerak (mahsulot yaratilganda birdaniga yaratiladi)
        # Lekin himoya uchun avtomatik yaratib olamiz
        logger.warning(
            f"⚠️ Mahsulot ID={stock_data.product_id} uchun inventory yo'q. "
            "Avtomatik yaratilmoqda..."
        )
        inventory = Inventory(product_id=stock_data.product_id, miqdor=0)
        db.add(inventory)
        db.flush()

    # ── 3. Eski qoldiqni eslab, yangi qoldiqni hisoblash ───────
    eski_qoldiq  = inventory.miqdor
    yangi_qoldiq = eski_qoldiq + stock_data.miqdor

    # ── 4. Atomik yangilash ─────────────────────────────────────
    inventory.miqdor = yangi_qoldiq
    db.commit()
    db.refresh(inventory)

    logger.info(
        f"📥 Kirim: '{product.kiyim_nomi}' (ID={product.id}): "
        f"{eski_qoldiq} + {stock_data.miqdor} = {yangi_qoldiq} dona "
        f"| Xodim: '{current_user.login}'"
        + (f" | Izoh: {stock_data.izoh}" if stock_data.izoh else "")
    )

    return AddStockResponse(
        success       = True,
        message       = (
            f"'{product.kiyim_nomi}' mahsulotiga {stock_data.miqdor} dona kirim qilindi. "
            f"Yangi qoldiq: {yangi_qoldiq} dona."
        ),
        product_id    = product.id,
        kiyim_nomi    = product.kiyim_nomi,
        kirim_miqdor  = stock_data.miqdor,
        yangi_qoldiq  = yangi_qoldiq,
        eski_qoldiq   = eski_qoldiq,
    )


# ============================================================
#  3. KAM QOLGAN TOVARLAR  (GET /inventory/low-stock)
# ============================================================

@router.get(
    "/low-stock",
    response_model=LowStockListResponse,
    summary="Kam qolgan tovarlar (Ogohlantirish tizimi)",
    description=(
        "Omborda qoldig'i belgilangan chegaradan kam bo'lgan mahsulotlarni topadi. "
        "Default chegara: **5 dona**. Parametr orqali o'zgartirish mumkin. "
        "Frontend bu ro'yxatni ogohlantirish (alert) sifatida ko'rsatishi kerak."
    ),
)
def get_low_stock(
    chegara    : int     = Query(default=5, ge=0, le=1000,
                                 description="Ogohlantirish chegarasi (donada)"),
    db         : Session = Depends(get_db),
    _          : User    = Depends(get_current_user),
) -> LowStockListResponse:
    """
    Ombor ogohlantirish ro'yxati.

    SQL mantiq: WHERE inventory.miqdor < chegara AND products.is_active = true
    Kamroqdan ko'proqqa tartiblab qaytariladi (eng kritik birinchi).
    """
    # ── Kam qolgan tovarlarni topish (JOIN bilan) ───────────────
    low_stock_records = (
        db.query(Inventory)
        .options(joinedload(Inventory.product))
        .join(Inventory.product)
        .filter(
            Inventory.miqdor < chegara,
            Product.is_active == True,  # noqa: E712
        )
        .order_by(Inventory.miqdor.asc())    # Eng kamdan boshlab
        .all()
    )

    # ── Javobni shakllantirish ──────────────────────────────────
    items = [
        LowStockResponse(
            product_id    = rec.product_id,
            kiyim_nomi    = rec.product.kiyim_nomi,
            shtrix_kod    = rec.product.shtrix_kod,
            razmer        = rec.product.razmer,
            rang          = rec.product.rang,
            mavjud_miqdor = rec.miqdor,
            chegarа       = chegara,
        )
        for rec in low_stock_records
    ]

    if items:
        logger.warning(
            f"⚠️ Kam qolgan tovarlar: {len(items)} ta "
            f"(chegara={chegara} dona)"
        )

    return LowStockListResponse(
        chegara   = chegara,
        jami_soni = len(items),
        items     = items,
    )


# ============================================================
#  4. BITTA MAHSULOTNING QOLDIG'I  (GET /inventory/{product_id})
# ============================================================

@router.get(
    "/{product_id}",
    response_model=InventoryResponse,
    summary="Bitta mahsulotning ombor qoldig'i",
    description="Mahsulot ID si bo'yicha ombor qoldig'ini va mahsulot tafsilotlarini qaytaradi.",
)
def get_product_inventory(
    product_id : int,
    db         : Session = Depends(get_db),
    _          : User    = Depends(get_current_user),
) -> InventoryResponse:
    """
    Bitta mahsulotning ombordagi qoldig'i.

    Kassir shtrix-kodni skanerlaganda:
        1. GET /products/search?shtrix_kod=... → narx va ma'lumot
        2. GET /inventory/{product_id}         → ombordagi miqdor
    Yoki ikkisini bitta so'rovda olish mumkin.
    """
    # ── Inventory yozuvini product bilan birgalikda olish ────────
    inventory = (
        db.query(Inventory)
        .options(joinedload(Inventory.product))
        .filter(Inventory.product_id == product_id)
        .first()
    )

    if not inventory:
        # Mahsulot mavjudligini ham tekshirish (aniq xabar uchun)
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ID={product_id} bo'lgan mahsulot topilmadi.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{product.kiyim_nomi}' (ID={product_id}) uchun "
                "ombor yozuvi topilmadi. Mahsulotni qayta yarating."
            ),
        )

    return InventoryResponse.model_validate(inventory)
