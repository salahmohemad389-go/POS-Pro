"""Permission system for POS Pro.

Role defaults remain the baseline, while individual users may have an explicit
permission list. The bootstrap owner account always keeps the full admin set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import User


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
        "user_view", "user_save", "delete_user", "user_revoke_sessions",
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

ALL_PERMISSIONS = frozenset().union(*PERMISSION_MATRIX.values())


def get_user_permissions(user: "User") -> frozenset[str]:
    """Return the effective permissions for a user.

    ``permissions`` is an optional per-user override. ``None`` means use role
    defaults; an empty list intentionally means no permissions.
    """
    if bool(getattr(user, "is_owner", False)):
        return PERMISSION_MATRIX["admin"]
    override = getattr(user, "permissions", None)
    if override is not None:
        if not isinstance(override, (list, tuple, set, frozenset)):
            return frozenset()
        return frozenset(str(x) for x in override if str(x) in ALL_PERMISSIONS)
    role = user.role or "cashier"
    return PERMISSION_MATRIX.get(role, frozenset())


def has_permission(user: "User", action: str) -> bool:
    return action in get_user_permissions(user)
