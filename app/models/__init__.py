"""
app/models/__init__.py
=======================
Barcha modellarni shu yerdan import qilish mumkin.
Bu alembic va database.py uchun ham muhim.
"""

from app.models.all_models import (
    Base,
    User,
    Product,
    Inventory,
    Customer,
    Invoice,
    InvoiceItem,
    UserRole,
    CustomerType,
    InvoiceStatus,
)

__all__ = [
    "User",
    "Product",
    "Inventory",
    "Customer",
    "Invoice",
    "InvoiceItem",
    "UserRole",
    "CustomerType",
    "InvoiceStatus",
]
