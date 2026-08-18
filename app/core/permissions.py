"""Permission system for POS Pro.

Single source of truth for role-based access control.
All permission checks throughout the app should use has_permission().

Roles:
  admin   - Full access to everything
  manager - All operations except user management, settings, audit clear, restore
  cashier - POS + view own invoices + view products/customers
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import User


# ═══════════════════════════════════════════════════
# Permission matrix (canonical)
# ═══════════════════════════════════════════════════
PERMISSION_MATRIX: dict[str, frozenset[str]] = {
    "admin": frozenset([
        "pos_view",
        "invoice_create", "invoice_view", "invoice_view_own",
        "invoice_collect", "invoice_edit", "invoice_delete",
        "product_view", "product_save", "product_delete",
        "product_import", "product_export",
        "customer_view", "customer_create", "customer_save",
        "customer_delete", "customer_export",
        "category_view", "category_save", "category_delete",
        "supplier_view", "supplier_save", "supplier_delete", "supplier_export",
        "user_view", "user_save", "delete_user",
        "settings_save",
        "backup_create", "backup_restore",
        "report_dashboard", "report_low_stock", "report_profit", "report_customer_debts",
        "audit_view", "audit_clear", "clear_data",
    ]),
    "manager": frozenset([
        "pos_view",
        "invoice_create", "invoice_view", "invoice_view_own",
        "invoice_collect", "invoice_edit",
        "product_view", "product_save", "product_delete",
        "product_import", "product_export",
        "customer_view", "customer_create", "customer_save",
        "customer_delete", "customer_export",
        "category_view", "category_save", "category_delete",
        "supplier_view", "supplier_save", "supplier_delete", "supplier_export",
        "user_view",
        "report_dashboard", "report_low_stock", "report_profit", "report_customer_debts",
        "backup_create", "audit_view",
    ]),
    "cashier": frozenset([
        "pos_view",
        "invoice_create", "invoice_view_own", "invoice_view",
        "invoice_collect", "invoice_edit",
        "product_view",
        "customer_view", "customer_create",
        "report_dashboard", "report_low_stock",
    ]),
}


def has_permission(user: "User", action: str) -> bool:
    """Check if the given user has a specific permission."""
    role = user.role or "cashier"
    return action in PERMISSION_MATRIX.get(role, frozenset())
