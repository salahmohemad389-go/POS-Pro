from __future__ import annotations
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

def test_all_javascript_parses():
    files = [STATIC / "app.js", STATIC / "js" / "upgrade_dom.js", STATIC / "js" / "upgrade_methods.js", *sorted((STATIC / "js" / "core").glob("*.js")), *sorted((STATIC / "js" / "pages").glob("*.js"))]
    assert files
    for file in files:
        cp = subprocess.run(["node", "--check", str(file)], text=True, capture_output=True)
        assert cp.returncode == 0, f"{file}: {cp.stderr}"

def test_page_modules_do_not_compose_peer_page_method_objects():
    page_dir = STATIC / "js" / "pages"; peer_spread = re.compile(r"\.\.\.[A-Za-z]+Methods\b"); offenders = {}
    for file in sorted(page_dir.glob("*.js")):
        matches = peer_spread.findall(file.read_text(encoding="utf-8"))
        if matches: offenders[file.name] = matches
    assert offenders == {}, f"Page modules must stay independent; compose them only in static/app.js: {offenders}"

def test_new_pos_branding_permissions_and_pdf_controls_are_wired():
    shell = (STATIC / "js" / "upgrade_dom.js").read_text(encoding="utf-8"); misc = (ROOT / "app" / "api" / "routes" / "misc.py").read_text(encoding="utf-8"); appjs = (STATIC / "app.js").read_text(encoding="utf-8"); upgrades = (STATIC / "js" / "upgrade_methods.js").read_text(encoding="utf-8"); products = (STATIC / "js" / "pages" / "products.js").read_text(encoding="utf-8")
    for element_id in ("loginLogoImg", "sidebarLogoImg", "toggleLoginPass", "posReturnBtn", "updatePricesInput", "pdfPreviewModal", "userExpiresAt", "userPermissionsGrid"): assert f'id="{element_id}"' in shell
    assert "upgrade_dom.js" in misc and "upgrade.css" in misc; assert "loadPublicBranding" in appjs; assert "feature_reports_enabled" in appjs and "feature_suppliers_enabled" in appjs; assert "row.addEventListener('click', add)" in upgrades; assert "المتاح فقط" in upgrades; assert "pdfPreviewFrame" in upgrades and "printPdfPreview" in upgrades; assert "upgradeMethods" in appjs; assert "/api/products/import-prices" in products

def test_combined_items_merge_same_product_in_source_order_and_net_returns():
    from types import SimpleNamespace
    from app.services.combined_invoice_service import _merge_items
    def inv(kind, items, **totals):
        defaults = dict(subtotal=0, discount=0, tax=0, total=0, paid=0); defaults.update(totals); return SimpleNamespace(type=kind, items=items, **defaults)
    sales1 = inv("sale", [{"product_id":1,"product_name":"A","unit":"قطعة","quantity":2,"unit_price":10,"total":20},{"product_id":2,"product_name":"B","unit":"قطعة","quantity":1,"unit_price":20,"total":20}], subtotal=40,total=40,paid=40)
    sales2 = inv("sale", [{"product_id":2,"product_name":"B","unit":"قطعة","quantity":2,"unit_price":25,"total":50},{"product_id":3,"product_name":"C","unit":"قطعة","quantity":1,"unit_price":30,"total":30}], subtotal=80,total=80,paid=80)
    returned = inv("return", [{"product_id":2,"product_name":"B","unit":"قطعة","quantity":1,"unit_price":20,"total":20}], subtotal=20,total=20,paid=20)
    items, totals = _merge_items([sales1,sales2,returned], {"deduct_returns":True}); assert [x["product_name"] for x in items] == ["A","B","C"]; assert [x["quantity"] for x in items] == [2.0,2.0,1.0]; assert items[1]["total"] == 50.0; assert items[1]["unit_price"] == 25.0; assert totals["total"] == 100.0

def test_frontend_has_no_external_runtime_dependencies_or_browser_token_storage():
    text = "\n".join(p.read_text(encoding="utf-8") for p in STATIC.rglob("*") if p.suffix in {".html", ".js", ".css"}); assert not re.search(r"https?://", text); lowered = text.lower();
    assert "localstorage.setitem('token" not in lowered; assert 'localstorage.setitem("token' not in lowered; assert "localstorage.setitem('pos_session" not in lowered; assert 'localstorage.setitem("pos_session' not in lowered; assert "sessionstorage.setitem('token" not in lowered; assert "authorization: `bearer" not in lowered

def test_no_product_image_feature_and_pos_uses_server_pdf():
    js = "\n".join(p.read_text(encoding="utf-8") for p in (STATIC / "js").rglob("*.js")); assert "product_image" not in js.lower(); assert "/api/products/image" not in js; invoices = (STATIC / "js" / "pages" / "invoices.js").read_text(encoding="utf-8"); appjs = (STATIC / "app.js").read_text(encoding="utf-8"); all_frontend = invoices + "\n" + appjs + "\n" + js; assert "/pdf" in invoices; assert "/pdf" in all_frontend; assert "window.print(" not in invoices

def test_server_owns_invoice_totals_frontend_sends_minimal_payload():
    pos = (STATIC / "js" / "pages" / "pos.js").read_text(encoding="utf-8"); payload_block = pos[pos.index("const payload = {"):pos.index("};", pos.index("const payload = {"))]
    for forbidden in ("subtotal,", "tax_rate:", "tax,", "total,", "remaining,"): assert forbidden not in payload_block
    assert "product_id: i.product_id" in payload_block; assert "quantity: i.quantity" in payload_block

def test_vercel_and_ci_files_are_safe_and_present():
    assert (ROOT / "server.py").exists(); assert not (ROOT / "app.py").exists(); assert (ROOT / ".python-version").read_text().strip() == "3.12"; conf = json.loads((ROOT / "vercel.json").read_text()); assert "tests/**" in conf["functions"]["server.py"]["excludeFiles"]; assert (ROOT / ".github" / "workflows" / "ci.yml").exists(); gitignore = (ROOT / ".gitignore").read_text();
    for required in (".env", "runtime/", "*.db", ".vercel/"): assert required in gitignore

def test_runtime_requirements_are_pinned_and_hardened():
    lines = [x.strip() for x in (ROOT / "requirements.txt").read_text().splitlines() if x.strip() and not x.startswith("#")]; assert lines; assert all("==" in x for x in lines); assert "defusedxml==0.7.1" in lines

def test_return_workflow_is_exposed_only_from_original_invoice():
    html = (STATIC / "index.html").read_text(encoding="utf-8"); invoices = (STATIC / "js" / "pages" / "invoices.js").read_text(encoding="utf-8"); pos = (STATIC / "js" / "pages" / "pos.js").read_text(encoding="utf-8"); assert 'id="returnInvoiceBtn"' in html; assert 'id="returnInvoiceModal"' in html; assert "/api/invoices/return-original-items/" in invoices; assert "API.post('/api/invoices/return'" in invoices; assert "/api/invoices/return" not in pos

def test_partial_payment_ui_and_backend_semantics_are_explicit():
    pos = (STATIC / "js" / "pages" / "pos.js").read_text(encoding="utf-8"); assert "paid <= 0 || paid >= total" in pos; service = (ROOT / "app" / "services" / "invoice_service.py").read_text(encoding="utf-8"); assert "الدفع الجزئي يجب أن يكون أكبر من صفر وأقل من إجمالي الفاتورة" in service; assert "المرتجع النقدي يجب أن يرد قيمة المرتجع كاملة" in service

def test_vercel_generated_hosts_are_trusted_without_broad_wildcard(monkeypatch):
    import importlib
    import app.core.config as cfg
    monkeypatch.setenv("POS_ENV", "development"); monkeypatch.setenv("VERCEL_URL", "pos-abc123.vercel.app"); monkeypatch.setenv("VERCEL_BRANCH_URL", "pos-git-feature.vercel.app"); monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "pos.vercel.app"); monkeypatch.setenv("POS_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"); monkeypatch.setenv("POS_ALLOWED_ORIGINS", "http://localhost:8000"); reloaded = importlib.reload(cfg)
    try:
        hosts = set(reloaded.POS_ALLOWED_HOSTS.split(",")); assert "pos-abc123.vercel.app" in hosts; assert "pos-git-feature.vercel.app" in hosts; assert "pos.vercel.app" in hosts; assert "*" not in hosts; assert "https://pos-abc123.vercel.app" in reloaded.CORS_ORIGINS; assert "https://pos.vercel.app" in reloaded.CORS_ORIGINS
    finally:
        monkeypatch.delenv("VERCEL_URL", raising=False); monkeypatch.delenv("VERCEL_BRANCH_URL", raising=False); monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False); importlib.reload(cfg)
