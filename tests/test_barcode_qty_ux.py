from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_quick_quantity_buttons_increment_current_quantity():
    market = (ROOT / "static" / "js" / "market_methods.js").read_text(encoding="utf-8")
    assert "setQtyToActive(delta)" in market
    assert "const current = Util.r3(parseFloat(last.quantity) || 0);" in market
    assert "let target = Util.r3(current + inc);" in market
    assert "last.quantity = target;" in market
    assert "import './barcode_ux.js';" in market


def test_barcode_search_supports_hardware_scanner_and_camera_fallback():
    barcode = (ROOT / "static" / "js" / "barcode_ux.js").read_text(encoding="utf-8")
    pos = (ROOT / "static" / "js" / "pages" / "pos.js").read_text(encoding="utf-8")
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")

    # USB/Bluetooth keyboard-wedge scanners submit into the POS search field.
    assert "pos_hardware_barcode_detected" in barcode
    assert "submitBarcode(value)" in barcode
    assert "KeyboardEvent('keydown', { key: 'Enter'" in barcode
    assert "/api/products/by-barcode/" in pos

    # Camera is a local browser fallback and does not depend on a third-party CDN.
    assert "BarcodeDetector" in barcode
    assert "navigator.mediaDevices.getUserMedia" in barcode
    assert "facingMode: { ideal: 'environment' }" in barcode
    assert "posCameraScanBtn" in barcode
    assert '"Permissions-Policy", "camera=(self), microphone=(), geolocation=()"' in main


def test_optional_invoice_contact_inputs_are_removed_from_pos():
    barcode = (ROOT / "static" / "js" / "barcode_ux.js").read_text(encoding="utf-8")
    assert "document.querySelectorAll('.invoice-optional-meta').forEach(el => el.remove())" in barcode
    assert "MutationObserver(removeLegacyOptionalInvoiceFields)" in barcode
