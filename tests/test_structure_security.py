from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def test_all_javascript_parses():
    files = [STATIC / "app.js", *sorted((STATIC / "js" / "core").glob("*.js")), *sorted((STATIC / "js" / "pages").glob("*.js"))]
    assert files
    for file in files:
        cp = subprocess.run(["node", "--check", str(file)], text=True, capture_output=True)
        assert cp.returncode == 0, f"{file}: {cp.stderr}"


def test_frontend_has_no_external_runtime_dependencies_or_browser_token_storage():
    text = "\n".join(p.read_text(encoding="utf-8") for p in STATIC.rglob("*") if p.suffix in {".html", ".js", ".css"})
    assert not re.search(r"https?://", text)
    # Theme preference may use localStorage; authentication/session data must not.
    lowered = text.lower()
    assert "localstorage.setitem('token" not in lowered
    assert 'localstorage.setitem("token' not in lowered
    assert "localstorage.setitem('pos_session" not in lowered
    assert 'localstorage.setitem("pos_session' not in lowered
    assert "sessionstorage.setitem('token" not in lowered
    assert "authorization: `bearer" not in lowered


def test_no_product_image_feature_and_pos_uses_server_pdf():
    js = "\n".join(p.read_text(encoding="utf-8") for p in (STATIC / "js").rglob("*.js"))
    assert "product_image" not in js.lower()
    assert "/api/products/image" not in js
    invoices = (STATIC / "js" / "pages" / "invoices.js").read_text(encoding="utf-8")
    appjs = (STATIC / "app.js").read_text(encoding="utf-8")
    all_frontend = invoices + "\n" + appjs + "\n" + js
    assert "/pdf" in invoices
    assert "/pdf" in all_frontend
    assert "window.print(" not in invoices


def test_server_owns_invoice_totals_frontend_sends_minimal_payload():
    pos = (STATIC / "js" / "pages" / "pos.js").read_text(encoding="utf-8")
    payload_block = pos[pos.index("const payload = {"):pos.index("};", pos.index("const payload = {"))]
    for forbidden in ("subtotal,", "tax_rate:", "tax,", "total,", "remaining,"):
        assert forbidden not in payload_block
    assert "product_id: i.product_id" in payload_block
    assert "quantity: i.quantity" in payload_block


def test_vercel_and_ci_files_are_safe_and_present():
    assert (ROOT / "app.py").exists()
    assert (ROOT / ".python-version").read_text().strip() == "3.12"
    conf = json.loads((ROOT / "vercel.json").read_text())
    assert "tests/**" in conf["functions"]["app.py"]["excludeFiles"]
    assert (ROOT / ".github" / "workflows" / "ci.yml").exists()
    gitignore = (ROOT / ".gitignore").read_text()
    for required in (".env", "runtime/", "*.db", ".vercel/"):
        assert required in gitignore


def test_runtime_requirements_are_pinned_and_hardened():
    lines = [x.strip() for x in (ROOT / "requirements.txt").read_text().splitlines() if x.strip() and not x.startswith("#")]
    assert lines
    assert all("==" in x for x in lines)
    assert "defusedxml==0.7.1" in lines


def test_return_workflow_is_exposed_only_from_original_invoice():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    invoices = (STATIC / "js" / "pages" / "invoices.js").read_text(encoding="utf-8")
    pos = (STATIC / "js" / "pages" / "pos.js").read_text(encoding="utf-8")
    assert 'id="returnInvoiceBtn"' in html
    assert 'id="returnInvoiceModal"' in html
    assert "/api/invoices/return-original-items/" in invoices
    assert "API.post('/api/invoices/return'" in invoices
    assert "/api/invoices/return" not in pos


def test_partial_payment_ui_and_backend_semantics_are_explicit():
    pos = (STATIC / "js" / "pages" / "pos.js").read_text(encoding="utf-8")
    assert "paid <= 0 || paid >= total" in pos
    service = (ROOT / "app" / "services" / "invoice_service.py").read_text(encoding="utf-8")
    assert "الدفع الجزئي يجب أن يكون أكبر من صفر وأقل من إجمالي الفاتورة" in service
    assert "المرتجع النقدي يجب أن يرد قيمة المرتجع كاملة" in service


def test_vercel_generated_hosts_are_trusted_without_broad_wildcard(monkeypatch):
    import importlib
    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    import app.core.config as cfg

    monkeypatch.setenv("POS_ENV", "development")
    monkeypatch.setenv("VERCEL_URL", "pos-abc123.vercel.app")
    monkeypatch.setenv("VERCEL_BRANCH_URL", "pos-git-feature.vercel.app")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "pos.vercel.app")
    monkeypatch.setenv("POS_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    monkeypatch.setenv("POS_ALLOWED_ORIGINS", "http://localhost:8000")
    reloaded = importlib.reload(cfg)
    try:
        hosts = set(reloaded.POS_ALLOWED_HOSTS.split(","))
        assert "pos-abc123.vercel.app" in hosts
        assert "pos-git-feature.vercel.app" in hosts
        assert "pos.vercel.app" in hosts
        assert "*" not in hosts
        assert "https://pos-abc123.vercel.app" in reloaded.CORS_ORIGINS
        assert "https://pos.vercel.app" in reloaded.CORS_ORIGINS
    finally:
        monkeypatch.delenv("VERCEL_URL", raising=False)
        monkeypatch.delenv("VERCEL_BRANCH_URL", raising=False)
        monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)
        importlib.reload(cfg)
