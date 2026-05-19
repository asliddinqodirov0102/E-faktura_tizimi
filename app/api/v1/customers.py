"""
app/api/v1/customers.py
========================
Mijozlar boshqaruvi uchun API Router.

Endpoint'lar:
    POST /api/v1/customers/       → Yangi mijoz qo'shish
    GET  /api/v1/customers/       → Mijozlar ro'yxati (qidiruv + sahifalash)
    GET  /api/v1/customers/{id}   → Bitta mijoz tafsiloti (faktura tarixi bilan)
    PUT  /api/v1/customers/{id}   → Mijoz ma'lumotlarini yangilash
"""

import logging
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.all_models import Customer, User
from app.schemas.all_schemas import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    MessageResponse,
)
from app.api.deps import get_current_user, get_kassir_or_admin
from pydantic import BaseModel
from typing import List
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customers", tags=["👤 Mijozlar"])


# ── Sahifalangan javob sxemasi ─────────────────────────────
class CustomerListPaginated(BaseModel):
    total  : int
    page   : int
    size   : int
    pages  : int
    items  : List[CustomerResponse]


# ============================================================
#  1. YANGI MIJOZ QO'SHISH  (POST /customers/)
# ============================================================

@router.post(
    "/",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yangi mijoz qo'shish",
    description=(
        "Yangi xaridor yoki kompaniyani tizimga kiritadi. "
        "Telefon raqami **noyob** bo'lishi kerak — dublikat qabul qilinmaydi. "
        "Admin yoki kassir bajara oladi."
    ),
)
def create_customer(
    customer_data : CustomerCreate,
    db            : Session = Depends(get_db),
    _             : User    = Depends(get_kassir_or_admin),
) -> CustomerResponse:
    """
    Yangi mijoz yaratish.

    Xatoliklar:
        400 → Bunday telefon raqami allaqachon ro'yxatda bor
        422 → Validatsiya xatosi (telefon formati, STIR noto'g'ri)
    """
    # ── Telefon noyobligini tekshirish ──────────────────────────
    existing = db.query(Customer).filter(
        Customer.telefon == customer_data.telefon
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{customer_data.telefon}' raqamli mijoz allaqachon mavjud. "
                f"(ID: {existing.id}, Ism: '{existing.ism_sharif}')"
            ),
        )

    # ── Yangi mijoz yaratish ────────────────────────────────────
    try:
        new_customer = Customer(
            ism_sharif  = customer_data.ism_sharif,
            telefon     = customer_data.telefon,
            mijoz_turi  = customer_data.mijoz_turi,
            stir_inn    = customer_data.stir_inn,
            manzil      = customer_data.manzil,
        )
        db.add(new_customer)
        db.commit()
        db.refresh(new_customer)

    except IntegrityError as e:
        db.rollback()
        logger.error(f"❌ Mijoz yaratishda IntegrityError: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telefon raqami allaqachon band yoki ma'lumotlar noto'g'ri.",
        )

    logger.info(
        f"✅ Yangi mijoz: '{new_customer.ism_sharif}' "
        f"tel={new_customer.telefon} tur={new_customer.mijoz_turi}"
    )
    return CustomerResponse.model_validate(new_customer)


# ============================================================
#  2. MIJOZLAR RO'YXATI  (GET /customers/)
# ============================================================

@router.get(
    "/",
    response_model=CustomerListPaginated,
    summary="Mijozlar ro'yxati va qidirish",
    description=(
        "Mijozlarni ism yoki telefon bo'yicha qidiradi. "
        "Sahifalash qo'llab-quvvatlanadi. "
        "Barcha autentifikatsiya qilingan xodimlar ko'ra oladi."
    ),
)
def list_customers(
    page       : int           = Query(default=1,   ge=1,       description="Sahifa raqami"),
    size       : int           = Query(default=20,  ge=1, le=100, description="Sahifadagi yozuvlar"),
    qidiruv    : Optional[str] = Query(default=None,             description="Ism yoki telefon bo'yicha qidirish"),
    mijoz_turi : Optional[str] = Query(default=None,             description="jismoniy | yuridik"),
    db         : Session       = Depends(get_db),
    _          : User          = Depends(get_current_user),
) -> CustomerListPaginated:
    """
    Mijozlar sahifalangan ro'yxati.

    Qidiruv bir vaqtda ism va telefon bo'yicha ishlaydi (OR shartli).
    """
    query = db.query(Customer)

    # ── Qidiruv filtri (ism yoki telefon) ─────────────────────
    if qidiruv:
        pattern = f"%{qidiruv.strip()}%"
        query = query.filter(
            Customer.ism_sharif.ilike(pattern) |
            Customer.telefon.ilike(pattern)
        )

    # ── Mijoz turi filtri ──────────────────────────────────────
    if mijoz_turi in ("jismoniy", "yuridik"):
        query = query.filter(Customer.mijoz_turi == mijoz_turi)

    # ── Sahifalash ─────────────────────────────────────────────
    total       = query.count()
    total_pages = math.ceil(total / size) if total > 0 else 1
    offset      = (page - 1) * size

    customers = (
        query
        .order_by(Customer.id.desc())
        .offset(offset)
        .limit(size)
        .all()
    )

    return CustomerListPaginated(
        total = total,
        page  = page,
        size  = size,
        pages = total_pages,
        items = [CustomerResponse.model_validate(c) for c in customers],
    )


# ============================================================
#  3. BITTA MIJOZ TAFSILOTI  (GET /customers/{id})
# ============================================================

@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Mijoz tafsiloti",
)
def get_customer(
    customer_id : int,
    db          : Session = Depends(get_db),
    _           : User    = Depends(get_current_user),
) -> CustomerResponse:
    """Mijoz ID si bo'yicha to'liq ma'lumot."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ID={customer_id} bo'lgan mijoz topilmadi.",
        )
    return CustomerResponse.model_validate(customer)


# ============================================================
#  4. MIJOZNI YANGILASH  (PUT /customers/{id})
# ============================================================

@router.put(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Mijoz ma'lumotlarini yangilash",
    description="Mijozning ism, telefon yoki manzilini yangilaydi. Admin yoki kassir bajara oladi.",
)
def update_customer(
    customer_id   : int,
    customer_data : CustomerUpdate,
    db            : Session = Depends(get_db),
    current_user  : User    = Depends(get_kassir_or_admin),
) -> CustomerResponse:
    """
    Mijoz ma'lumotlarini qisman yangilash.
    Faqat yuborilgan maydonlar o'zgartiriladi.
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ID={customer_id} bo'lgan mijoz topilmadi.",
        )

    # ── Agar telefon o'zgarayotgan bo'lsa, noyobligini tekshirish ──
    update_fields = customer_data.model_dump(exclude_unset=True)
    if "telefon" in update_fields:
        existing = db.query(Customer).filter(
            Customer.telefon == update_fields["telefon"],
            Customer.id != customer_id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{update_fields['telefon']}' telefon raqami allaqachon boshqa mijozda mavjud.",
            )

    try:
        for field, value in update_fields.items():
            setattr(customer, field, value)
        db.commit()
        db.refresh(customer)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Yangilashda xatolik. Telefon raqami noyob bo'lishi kerak.",
        )

    logger.info(
        f"✏️ Mijoz yangilandi: ID={customer_id} "
        f"| Xodim: '{current_user.login}'"
    )
    return CustomerResponse.model_validate(customer)
