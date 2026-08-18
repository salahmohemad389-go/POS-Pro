"""PDF service for POS Pro - generates invoice PDFs.

Provides the public PDF service interface for the API layer.
Rendering lives in app.services.pdf_renderer; combined invoices are handled by app.services.combined_invoice_service.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("pospro.services.pdf")

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
FONT_DIR = STATIC_DIR / "assets" / "fonts"


def generate_invoice_pdf(
    invoice: Any,
    settings: dict[str, Any],
    *,
    page_size: str = "a4",
    items_per_page: int = 17,
) -> bytes:
    """Generate a PDF for a single invoice."""
    from app.services.pdf_renderer import generate_invoice_pdf as _gen
    return _gen(
        invoice=invoice,
        settings=settings,
        font_dir=FONT_DIR,
        page_size=page_size,
        items_per_page=items_per_page,
    )
