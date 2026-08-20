from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_a4_invoice_header_is_side_by_side_and_denser():
    source = (ROOT / "app" / "services" / "market_pdf_tuning.py").read_text(encoding="utf-8")
    assert "Table([[identity, logo]]" in source
    assert "30 * mm, 20 * mm" in source
    assert "effective_rows = max(21, effective_rows)" in source
    assert "content_w < 100 * mm" in source
    assert '" ".join(str(value or "").split())' in source


def test_mobile_invoice_preview_and_pdf_file_share_exist():
    source = (ROOT / "static" / "js" / "market_methods.js").read_text(encoding="utf-8")
    assert "100dvh" in source
    assert "pdfPreviewOpenBtn" in source
    assert "pdfPreviewShareBtn" in source
    assert "navigator.share" in source
    assert "navigator.canShare" in source
    assert "new File([prepared.blob]" in source
    assert "downloadBlob(prepared.blob" in source
    assert "data-share-inv" in source
