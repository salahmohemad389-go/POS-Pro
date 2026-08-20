"""Small final invoice-density tuning for the pre-market build."""
from __future__ import annotations

_INSTALLED = False


def install_market_pdf_tuning() -> None:
    """Fill otherwise-unused A4 space with symmetric item rows.

    Thermal receipts keep their natural height. A4 gets at least 18 item boxes,
    while any owner-selected larger page size remains respected.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    from app.services import pdf_renderer as pr

    original_items_table = pr._items_table

    def items_table_market(invoice, content_w, regular, bold, *, thermal: bool, items_per_page: int):
        effective_rows = int(items_per_page or 0)
        if not thermal:
            effective_rows = max(18, effective_rows)
        return original_items_table(
            invoice,
            content_w,
            regular,
            bold,
            thermal=thermal,
            items_per_page=effective_rows,
        )

    pr._items_table = items_table_market
    pr._market_pdf_density_v5 = True
    _INSTALLED = True
