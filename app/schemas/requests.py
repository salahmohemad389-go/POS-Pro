from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class CleanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProductSave(CleanModel):
    id: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=300)
    barcode: str = Field(default="", max_length=80)
    code: str = Field(default="", max_length=80)
    category_id: int | None = Field(default=None, ge=1)
    supplier_id: int | None = Field(default=None, ge=1)
    unit: str = Field(default="قطعة", min_length=1, max_length=40)
    cost: float = Field(default=0, ge=0, le=999999999.99)
    price: float = Field(default=0, ge=0, le=999999999.99)
    stock: float = Field(default=0, ge=0, le=999999999.999)
    min_stock: float = Field(default=5, ge=0, le=999999999.999)


class CategorySave(CleanModel):
    id: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=200)
    parent_id: int | None = Field(default=None, ge=1)


class SettingsSave(CleanModel):
    store_name: str | None = Field(default=None, max_length=200)
    branch: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=300)
    currency: str | None = Field(default=None, min_length=1, max_length=20)
    footer: str | None = Field(default=None, max_length=300)
    logo: str | None = Field(default=None, max_length=2_000_000)
    header_position: Literal["top", "center", "left", "right"] | None = None
    quick_qty: str | None = Field(default=None, max_length=200)
    printer_type: Literal["browser", "thermal"] | None = None
    theme: Literal["light", "dark"] | None = None
    tagline: str | None = Field(default=None, max_length=200)
    slogan: str | None = Field(default=None, max_length=200)
    custom_lines: str | None = Field(default=None, max_length=4000)
    invoice_format: Literal["a4", "thermal"] | None = None
    header_note: str | None = Field(default=None, max_length=200)
    terms_conditions: str | None = Field(default=None, max_length=5000)
    warranty_text: str | None = Field(default=None, max_length=300)
    max_items_per_page: int | None = Field(default=None, ge=5, le=100)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    vat_enabled: StrictBool | None = None
    copies: int | None = Field(default=None, ge=1, le=10)
    auto_print_after_sale: StrictBool | None = None
    feature_reports_enabled: StrictBool | None = None
    feature_suppliers_enabled: StrictBool | None = None
    ui_config: dict[str, object] | None = None

    @field_validator("logo")
    @classmethod
    def validate_logo(cls, value: str | None):
        if value in (None, ""):
            return value
        import base64
        prefixes = {
            "data:image/png;base64,": b"\x89PNG\r\n\x1a\n",
            "data:image/jpeg;base64,": b"\xff\xd8\xff",
            "data:image/gif;base64,": b"GIF8",
            "data:image/webp;base64,": b"RIFF",
        }
        prefix = next((p for p in prefixes if value.startswith(p)), None)
        if not prefix:
            raise ValueError("الشعار يجب أن يكون صورة PNG/JPEG/GIF/WEBP")
        try:
            raw = base64.b64decode(value[len(prefix):], validate=True)
        except Exception as exc:
            raise ValueError("بيانات الشعار غير صالحة") from exc
        if not raw.startswith(prefixes[prefix]):
            raise ValueError("توقيع ملف الشعار لا يطابق نوع الصورة")
        if prefix.startswith("data:image/webp") and (len(raw) < 12 or raw[8:12] != b"WEBP"):
            raise ValueError("ملف WEBP غير صالح")
        if len(raw) > 1_500_000:
            raise ValueError("حجم الشعار أكبر من المسموح")
        return value


class SaleItem(CleanModel):
    product_id: int = Field(ge=1)
    quantity: float = Field(gt=0, le=999999999.999)


class InvoiceCreate(CleanModel):
    type: Literal["sale"] = "sale"
    customer_id: int | None = Field(default=None, ge=1)
    customer_name: str = Field(default="", max_length=200)
    customer_phone: str = Field(default="", max_length=40)
    discount_pct: float = Field(default=0, ge=0, le=100)
    payment_method: Literal["cash", "credit", "partial"] = "cash"
    paid: float | None = Field(default=None, ge=0, le=999999999.99)
    items: list[SaleItem] = Field(min_length=1, max_length=1000)


class ProductFind(CleanModel):
    q: str = Field(min_length=1, max_length=300)


class CollectPayment(CleanModel):
    amount: float = Field(gt=0, le=999999999.99)


class ReturnItem(CleanModel):
    product_id: int = Field(ge=1)
    quantity: float = Field(gt=0, le=999999999.999)


class ReturnCreate(CleanModel):
    customer_id: int = Field(ge=1)
    original_invoice_id: int = Field(ge=1)
    items: list[ReturnItem] = Field(min_length=1, max_length=1000)
    payment_method: Literal["cash", "credit", "partial"] = "cash"
    paid: float | None = Field(default=None, ge=0, le=999999999.99)
    notes: str = Field(default="", max_length=1000)


class LoginRequest(CleanModel):
    login: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=1024)


class ChangeCredentials(CleanModel):
    login: str | None = Field(default=None, min_length=1, max_length=80)
    password: str | None = Field(default=None, max_length=1024)
    current_password: str | None = Field(default=None, max_length=1024)


class UserSave(CleanModel):
    id: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=120)
    login: str = Field(min_length=1, max_length=80)
    role: Literal["admin", "manager", "cashier"] = "cashier"
    password: str = Field(default="", max_length=1024)
    active: StrictBool = True
    expires_at: datetime | None = None
    permissions: list[str] | None = Field(default=None, max_length=100)

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: list[str] | None):
        if value is None:
            return None
        from app.core.permissions import ALL_PERMISSIONS
        cleaned = list(dict.fromkeys(str(x).strip() for x in value if str(x).strip()))
        invalid = [x for x in cleaned if x not in ALL_PERMISSIONS]
        if invalid:
            raise ValueError("صلاحيات غير معروفة: " + ", ".join(invalid[:5]))
        return cleaned


class CustomerSave(CleanModel):
    id: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=4000)


class SupplierSave(CleanModel):
    id: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=120)
    address: str = Field(default="", max_length=4000)
    notes: str = Field(default="", max_length=4000)


class BackupRestore(CleanModel):
    name: str = Field(min_length=1, max_length=255, pattern=r"^backup_[A-Za-z0-9_.-]+\.zip$")


class CombinedOptions(CleanModel):
    include_details: StrictBool = True
    print_summary: StrictBool = True
    deduct_returns: StrictBool = True
    show_paid_remaining: StrictBool = True
    save_to_customer: StrictBool = True


class CombinedCreate(CleanModel):
    ids: list[int] = Field(min_length=2, max_length=50)
    options: CombinedOptions = Field(default_factory=CombinedOptions)

    @field_validator("ids")
    @classmethod
    def validate_ids(cls, value: list[int]):
        if any(int(x) <= 0 for x in value):
            raise ValueError("معرفات الفواتير يجب أن تكون أرقام موجبة")
        if len(set(value)) != len(value):
            raise ValueError("لا يجوز تكرار نفس الفاتورة في الدمج")
        return value