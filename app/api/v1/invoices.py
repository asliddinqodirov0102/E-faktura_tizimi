"""
app/api/v1/invoices.py
=======================
Elektron Hisob-Faktura (Sotuv Tranzaksiyasi) Router.

Endpoint'lar:
    POST /api/v1/invoices/              → Yangi faktura yaratish (sotuv)
    GET  /api/v1/invoices/              → Fakturalar ro'yxati (filtrlash bilan)
    GET  /api/v1/invoices/{id}          → Bitta faktura to'liq tafsiloti
    PUT  /api/v1/invoices/{id}/status   → Faktura statusini yangilash (to'langan)
    PUT  /api/v1/invoices/{id}/cancel   → Fakturani bekor qilish + inventoryni tiklash

═══════════════════════════════════════════════════════════
TRANZAKSIYA ARXITEKTURASI (CREATE INVOICE):
═══════════════════════════════════════════════════════════

  POST /invoices/ so'rovi keladi
       │
       ├─ 1. Mijoz mavjudligini tekshirish
       │
       ├─ 2. Har bir mahsulot uchun:
       │      ├─ SELECT ... FOR UPDATE NOWAIT  ← ROW LOCK (race condition oldini olish)
       │      ├─ Ombor qoldig'i yetarlimi?
       │      └─ YETARLI EMAS → HTTPException 400 (rollback avtomatik)
       │
       ├─ 3. Inventory'dan miqdor ayirish (atomik)
       │
       ├─ 4. InvoiceItem'larni yaratish (sotilgan vaqtdagi narx bilan)
       │
       ├─ 5. Umumiy summani hisoblash
       │
       ├─ 6. Noyob faktura raqamini generatsiya qilish
       │
       ├─ 7. Invoice yaratish
       │
       └─ 8. db.commit() ← Hamma o'zgarish birgalikda saqlanadi

═══════════════════════════════════════════════════════════
BEKOR QILISH ARXITEKTURASI (CANCEL INVOICE):
═══════════════════════════════════════════════════════════

  PUT /invoices/{id}/cancel
       │
       ├─ Faktura "kutilmoqda" statusida ekanligini tekshirish
       ├─ Har bir InvoiceItem uchun: inventory.miqdor += item.miqdor
       ├─ Invoice.status = "bekor_qilingan"
       └─ db.commit()
"""

import logging
import math
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import OperationalError

from app.core.database import get_db
from app.core.security import generate_invoice_number
from app.models.all_models import (
    Customer, Invoice, InvoiceItem, Inventory, Product, User,
    InvoiceStatus,
)
from app.schemas.all_schemas import (
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceResponse,
    InvoiceListResponse,
    MessageResponse,
)
from app.api.deps import get_current_user, get_kassir_or_admin, get_admin_user
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invoices", tags=["🧾 Hisob-Fakturalar"])


# ── Sahifalangan ro'yxat sxemasi ───────────────────────────
class InvoiceListPaginated(BaseModel):
    total  : int
    page   : int
    size   : int
    pages  : int
    items  : List[InvoiceListResponse]


# ── Status yangilash sxemasi ───────────────────────────────
class InvoiceStatusUpdate(BaseModel):
    status : InvoiceStatus


# ============================================================
#  1. YANGI FAKTURA YARATISH — SOTUV TRANZAKSIYASI
#     POST /invoices/
# ============================================================

@router.post(
    "/",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yangi faktura yaratish (Sotuv)",
    description=(
        "Sotuv tranzaksiyasini amalga oshiradi. "
        "**SELECT FOR UPDATE** orqali har bir tovar qatori qulflanadi — "
        "bir vaqtning o'zida ikki kassir bir xil tovarni sotoladigan "
        "'race condition' holati oldini olinadi. "
        "Biror mahsulot yetarli bo'lmasa, BUTUN sotuv bekor qilinadi."
    ),
)
def create_invoice(
    invoice_data : InvoiceCreate,
    db           : Session = Depends(get_db),
    current_user : User    = Depends(get_kassir_or_admin),
) -> InvoiceResponse:
    """
    Atomik sotuv tranzaksiyasi.

    Xatoliklar:
        400 → Mijoz topilmadi
        400 → Mahsulot topilmadi yoki faol emas
        400 → Omborda yetarli miqdor yo'q
        409 → Faktura raqami to'qnashuvi (qayta uriniladi)
        423 → Inventory qatori boshqa tranzaksiya tomonidan qulflangan
    """
    # ── 1. Mijoz mavjudligini tekshirish ───────────────────────
    customer = db.query(Customer).filter(
        Customer.id == invoice_data.customer_id
    ).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ID={invoice_data.customer_id} bo'lgan mijoz topilmadi.",
        )

    # ── 2. Takror product_id larni tekshirish ──────────────────
    product_ids = [item.product_id for item in invoice_data.items]
    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Bir fakturada bir xil mahsulot ikki marta kiritilgan. "
                "Iltimos, miqdorlarni birlashtiring."
            ),
        )

    # ── 3. Mahsulotlarni va inventory'ni QULFLASH ──────────────
    # SELECT FOR UPDATE NOWAIT:
    #   - FOR UPDATE     → Bu qatorni boshqa tranzaksiya o'zgartira olmaydi
    #   - NOWAIT         → Agar qulflangan bo'lsa, kutmasdan xato qaytaradi
    # Bu "race condition"ni to'liq bartaraf etadi.
    locked_inventories = {}   # product_id → Inventory obyekti
    products_map       = {}   # product_id → Product obyekti

    try:
        for item_data in invoice_data.items:
            # Mahsulotni olish
            product = db.query(Product).filter(
                Product.id      == item_data.product_id,
                Product.is_active == True,               # noqa: E712
            ).first()

            if not product:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"ID={item_data.product_id} bo'lgan mahsulot topilmadi "
                        "yoki faol emas. Sotuv bekor qilindi."
                    ),
                )

            # Inventory qatorini ROW LOCK bilan olish
            inventory = (
                db.query(Inventory)
                .filter(Inventory.product_id == item_data.product_id)
                .with_for_update(nowait=True)    # ← QULFLASH (NOWAIT)
                .first()
            )

            if not inventory:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"'{product.kiyim_nomi}' uchun ombor yozuvi topilmadi.",
                )

            # ── Yetarliligini tekshirish ─────────────────────────
            if inventory.miqdor < item_data.miqdor:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"'{product.kiyim_nomi}' uchun omborda yetarli miqdor yo'q. "
                        f"So'ralgan: {item_data.miqdor} dona, "
                        f"Mavjud: {inventory.miqdor} dona. "
                        "Sotuv bekor qilindi."
                    ),
                )

            locked_inventories[item_data.product_id] = inventory
            products_map[item_data.product_id]        = product

    except OperationalError:
        # NOWAIT xatosi: boshqa tranzaksiya shu qatorni qullagan
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "Ombor ma'lumotlari boshqa operatsiya tomonidan yangilanmoqda. "
                "Bir necha soniyadan keyin qayta urinib ko'ring."
            ),
        )

    # ── 4. Inventory'dan miqdorlarni ayirish va InvoiceItem'lar yaratish ──
    invoice_items = []
    umumiy_summa  = 0.0

    for item_data in invoice_data.items:
        inventory = locked_inventories[item_data.product_id]
        product   = products_map[item_data.product_id]

        # Ombordan ayirish
        inventory.miqdor -= item_data.miqdor

        # Sotilgan vaqtdagi narxni saqlash (tarixiy ma'lumot)
        kiyim_narxi = product.sotilish_narxi
        jami        = round(kiyim_narxi * item_data.miqdor, 2)
        umumiy_summa += jami

        invoice_item = InvoiceItem(
            product_id  = item_data.product_id,
            miqdor      = item_data.miqdor,
            kiyim_narxi = kiyim_narxi,
            jami        = jami,
        )
        invoice_items.append(invoice_item)

    # ── 5. Noyob faktura raqami generatsiya qilish ─────────────
    # Takror bo'lmasligi uchun 3 marta urinish
    faktura_raqami = None
    for _ in range(3):
        candidate = generate_invoice_number()
        exists = db.query(Invoice).filter(
            Invoice.faktura_raqami == candidate
        ).first()
        if not exists:
            faktura_raqami = candidate
            break

    if not faktura_raqami:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Faktura raqami generatsiyasida xatolik. Qayta urinib ko'ring.",
        )

    # ── 6. Invoice yaratish ────────────────────────────────────
    new_invoice = Invoice(
        faktura_raqami = faktura_raqami,
        customer_id    = invoice_data.customer_id,
        user_id        = current_user.id,
        umumiy_summa   = round(umumiy_summa, 2),
        status         = InvoiceStatus.kutilmoqda,
        izoh           = invoice_data.izoh,
    )
    db.add(new_invoice)
    db.flush()   # Invoice ID si generatsiya bo'ladi

    # InvoiceItem'larga invoice_id ni biriktirish
    for item in invoice_items:
        item.invoice_id = new_invoice.id
        db.add(item)

    # ── 7. Hamma o'zgarishni BIRGALIKDA saqlash ───────────────
    db.commit()

    # Javob uchun barcha aloqali ma'lumotlarni yuklash
    db.refresh(new_invoice)
    complete_invoice = (
        db.query(Invoice)
        .options(
            joinedload(Invoice.mijoz),
            joinedload(Invoice.xodim),
            selectinload(Invoice.items).joinedload(InvoiceItem.product),
        )
        .filter(Invoice.id == new_invoice.id)
        .first()
    )

    logger.info(
        f"✅ Yangi faktura: '{faktura_raqami}' "
        f"summa={umumiy_summa:,.0f} so'm, "
        f"{len(invoice_items)} ta mahsulot qatori "
        f"| Kassir: '{current_user.login}'"
    )
    return InvoiceResponse.model_validate(complete_invoice)


# ============================================================
#  2. FAKTURALAR RO'YXATI  (GET /invoices/)
# ============================================================

@router.get(
    "/",
    response_model=InvoiceListPaginated,
    summary="Fakturalar ro'yxati (filtrlash bilan)",
    description=(
        "Barcha fakturalarni ko'rsatadi. "
        "Sana oralig'i, status yoki mijoz bo'yicha filtrlash mumkin."
    ),
)
def list_invoices(
    page        : int                    = Query(default=1,   ge=1),
    size        : int                    = Query(default=20,  ge=1, le=100),
    status_f    : Optional[InvoiceStatus]= Query(default=None, alias="status",
                                                  description="Holat bo'yicha filtrlash"),
    customer_id : Optional[int]          = Query(default=None, description="Mijoz ID si"),
    sana_dan    : Optional[datetime]     = Query(default=None, description="Boshlanish sanasi (ISO 8601)"),
    sana_gacha  : Optional[datetime]     = Query(default=None, description="Tugash sanasi (ISO 8601)"),
    db          : Session                = Depends(get_db),
    _           : User                   = Depends(get_current_user),
) -> InvoiceListPaginated:
    """
    Fakturalar filtrlangan va sahifalangan ro'yxati.

    Misol:
        GET /invoices/?status=kutilmoqda&sana_dan=2024-01-01
    """
    query = (
        db.query(Invoice)
        .options(joinedload(Invoice.mijoz))
        .order_by(Invoice.yaratilgan_sana.desc())
    )

    if status_f:
        query = query.filter(Invoice.status == status_f)

    if customer_id:
        query = query.filter(Invoice.customer_id == customer_id)

    if sana_dan:
        dt = sana_dan if sana_dan.tzinfo else sana_dan.replace(tzinfo=timezone.utc)
        query = query.filter(Invoice.yaratilgan_sana >= dt)

    if sana_gacha:
        dt = sana_gacha if sana_gacha.tzinfo else sana_gacha.replace(tzinfo=timezone.utc)
        query = query.filter(Invoice.yaratilgan_sana <= dt)

    total       = query.count()
    total_pages = math.ceil(total / size) if total > 0 else 1
    offset      = (page - 1) * size

    invoices = query.offset(offset).limit(size).all()

    return InvoiceListPaginated(
        total = total,
        page  = page,
        size  = size,
        pages = total_pages,
        items = [InvoiceListResponse.model_validate(inv) for inv in invoices],
    )


# ============================================================
#  3. BITTA FAKTURA TO'LIQ TAFSILOTI  (GET /invoices/{id})
# ============================================================

@router.get(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Faktura to'liq tafsiloti",
    description=(
        "Fakturaning barcha ma'lumotlarini qaytaradi: "
        "mijoz, xodim, va har bir mahsulot qatori (narxi va miqdori bilan)."
    ),
)
def get_invoice(
    invoice_id : int,
    db         : Session = Depends(get_db),
    _          : User    = Depends(get_current_user),
) -> InvoiceResponse:
    """
    Bitta faktura to'liq ko'rinishi.
    selectinload + joinedload → bitta so'rovda nested ma'lumotlar.
    """
    invoice = (
        db.query(Invoice)
        .options(
            joinedload(Invoice.mijoz),
            joinedload(Invoice.xodim),
            selectinload(Invoice.items).joinedload(InvoiceItem.product),
        )
        .filter(Invoice.id == invoice_id)
        .first()
    )

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ID={invoice_id} bo'lgan faktura topilmadi.",
        )

    return InvoiceResponse.model_validate(invoice)


# ============================================================
#  4. FAKTURA STATUS YANGILASH  (PUT /invoices/{id}/status)
# ============================================================

@router.put(
    "/{invoice_id}/status",
    response_model=InvoiceResponse,
    summary="Faktura statusini yangilash (to'langan)",
    description=(
        "Faktura statusini `kutilmoqda` → `tolangan` ga o'tkazadi. "
        "Bekor qilingan fakturani qayta faollashtirib bo'lmaydi."
    ),
)
def update_invoice_status(
    invoice_id  : int,
    status_data : InvoiceStatusUpdate,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_kassir_or_admin),
) -> InvoiceResponse:
    """
    Faktura to'lov statusini yangilash.

    Qoidalar:
        - bekor_qilingan → boshqa statusga o'tkazib bo'lmaydi
        - tolangan → kutilmoqda'ga qaytarib bo'lmaydi
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ID={invoice_id} bo'lgan faktura topilmadi.",
        )

    if invoice.status == InvoiceStatus.bekor_qilingan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bekor qilingan faktura statusini o'zgartirib bo'lmaydi.",
        )

    if status_data.status == InvoiceStatus.bekor_qilingan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fakturani bekor qilish uchun '/cancel' endpoint'ini ishlating.",
        )

    eski_status     = invoice.status
    invoice.status  = status_data.status
    db.commit()
    db.refresh(invoice)

    logger.info(
        f"📝 Faktura '{invoice.faktura_raqami}' status: "
        f"{eski_status} → {invoice.status} "
        f"| Xodim: '{current_user.login}'"
    )

    complete = (
        db.query(Invoice)
        .options(
            joinedload(Invoice.mijoz),
            joinedload(Invoice.xodim),
            selectinload(Invoice.items).joinedload(InvoiceItem.product),
        )
        .filter(Invoice.id == invoice_id)
        .first()
    )
    return InvoiceResponse.model_validate(complete)


# ============================================================
#  5. FAKTURANI BEKOR QILISH  (PUT /invoices/{id}/cancel)
# ============================================================

@router.put(
    "/{invoice_id}/cancel",
    response_model=InvoiceResponse,
    summary="Fakturani bekor qilish (Inventory qaytariladi)",
    description=(
        "Fakturani bekor qiladi va fakturadagi **barcha mahsulotlar miqdori "
        "omborga qaytarib qo'yiladi** (atomik tranzaksiya). "
        "Faqat `kutilmoqda` statusidagi fakturalarni bekor qilish mumkin."
    ),
)
def cancel_invoice(
    invoice_id   : int,
    db           : Session = Depends(get_db),
    current_user : User    = Depends(get_kassir_or_admin),
) -> InvoiceResponse:
    """
    Fakturani bekor qilish tranzaksiyasi.

    Jarayon:
        1. Fakturani qulflash (FOR UPDATE)
        2. Status tekshirish (faqat kutilmoqda bekor qilinadi)
        3. Har bir InvoiceItem uchun: inventory.miqdor += item.miqdor
        4. Invoice.status = bekor_qilingan
        5. db.commit() — hamma birgalikda

    Xatoliklar:
        404 → Faktura topilmadi
        400 → Allaqachon bekor qilingan
        400 → To'langan fakturani bekor qilib bo'lmaydi (admin kerak)
    """
    # ── Fakturani qulflash (boshqa tranzaksiya o'zgartirmasin) ──
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id)
        .with_for_update()
        .first()
    )

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ID={invoice_id} bo'lgan faktura topilmadi.",
        )

    if invoice.status == InvoiceStatus.bekor_qilingan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{invoice.faktura_raqami}' fakturasi allaqachon bekor qilingan.",
        )

    if invoice.status == InvoiceStatus.tolangan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{invoice.faktura_raqami}' to'langan fakturani bekor qilish uchun "
                "administrator ruxsati kerak. Admin bilan bog'laning."
            ),
        )

    # ── InvoiceItem'larni yuklash va inventory'ni tiklash ──────
    items = (
        db.query(InvoiceItem)
        .filter(InvoiceItem.invoice_id == invoice_id)
        .all()
    )

    restored_count = 0
    for item in items:
        inventory = (
            db.query(Inventory)
            .filter(Inventory.product_id == item.product_id)
            .with_for_update()
            .first()
        )
        if inventory:
            inventory.miqdor += item.miqdor
            restored_count   += item.miqdor
            logger.info(
                f"  ↩️  product_id={item.product_id}: "
                f"+{item.miqdor} dona omborga qaytarildi "
                f"(yangi qoldiq: {inventory.miqdor})"
            )
        else:
            logger.warning(
                f"  ⚠️  product_id={item.product_id} uchun inventory yozuvi "
                "topilmadi — qaytarilmadi!"
            )

    # ── Faktura statusini yangilash ─────────────────────────────
    invoice.status = InvoiceStatus.bekor_qilingan
    db.commit()

    logger.info(
        f"🚫 Faktura bekor qilindi: '{invoice.faktura_raqami}' "
        f"({restored_count} dona omborga qaytarildi) "
        f"| Xodim: '{current_user.login}'"
    )

    complete = (
        db.query(Invoice)
        .options(
            joinedload(Invoice.mijoz),
            joinedload(Invoice.xodim),
            selectinload(Invoice.items).joinedload(InvoiceItem.product),
        )
        .filter(Invoice.id == invoice_id)
        .first()
    )
    return InvoiceResponse.model_validate(complete)
