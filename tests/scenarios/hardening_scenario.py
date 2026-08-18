import os, tempfile, pathlib
root = pathlib.Path(tempfile.mkdtemp(prefix="pos34hard_"))
os.environ["POS_DATABASE_URL"] = f"sqlite:///{root/'test.db'}"
os.environ["POS_ADMIN_PASSWORD"] = "AdminPassword#12345"
os.environ["POS_JWT_SECRET"] = "h" * 64
os.environ["POS_ALLOWED_HOSTS"] = "testserver"
os.environ["POS_ALLOWED_ORIGINS"] = "http://testserver"
os.environ["POS_RUNTIME_DIR"] = str(root / "runtime")

from fastapi.testclient import TestClient
from app.main import app
import app.api.routes.invoices as invoice_routes
import app.api.routes.settings as settings_routes

with TestClient(app) as c:
    def ck(r, code=200):
        assert r.status_code == code, (r.status_code, r.text)
        return r

    ck(c.post("/api/auth/login", json={"login": "admin", "password": "AdminPassword#12345"}))
    p = ck(c.post("/api/products", json={"name": "VAT Item", "price": 100, "cost": 50, "stock": 10})).json()["id"]
    cust = ck(c.post("/api/customers", json={"name": "VAT Customer"})).json()["id"]

    # Historical VAT must remain frozen on the issued invoice and its return.
    ck(c.post("/api/settings", json={"vat_enabled": True, "tax_rate": 14}))
    sale = ck(c.post("/api/invoices", json={
        "customer_id": cust,
        "payment_method": "cash",
        "items": [{"product_id": p, "quantity": 1}],
    })).json()
    inv = ck(c.get(f"/api/invoices/{sale['id']}" )).json()
    assert inv["subtotal"] == 100 and inv["tax_rate"] == 14 and inv["tax"] == 14 and inv["total"] == 114, inv

    ck(c.post("/api/settings", json={"vat_enabled": False}))
    frozen = ck(c.get(f"/api/invoices/{sale['id']}" )).json()
    assert frozen["tax_rate"] == 14 and frozen["tax"] == 14 and frozen["total"] == 114, frozen
    ret = ck(c.post("/api/invoices/return", json={
        "customer_id": cust,
        "original_invoice_id": sale["id"],
        "items": [{"product_id": p, "quantity": 1}],
        "payment_method": "cash",
    })).json()
    ret_inv = ck(c.get(f"/api/invoices/{ret['id']}" )).json()
    assert ret_inv["tax_rate"] == 14 and abs(ret_inv["tax"]) == 14 and abs(ret_inv["total"]) == 114 and abs(ret_inv["paid"]) == 114, ret_inv

    # New invoices after VAT is disabled must be tax-free.
    sale2 = ck(c.post("/api/invoices", json={
        "customer_id": cust,
        "payment_method": "cash",
        "items": [{"product_id": p, "quantity": 1}],
    })).json()
    inv2 = ck(c.get(f"/api/invoices/{sale2['id']}" )).json()
    assert inv2["tax_rate"] == 0 and inv2["tax"] == 0 and inv2["total"] == 100, inv2

    # Payment method semantics must be strict rather than silently changing meaning.
    ck(c.post("/api/invoices", json={
        "customer_id": cust, "payment_method": "partial", "paid": 0,
        "items": [{"product_id": p, "quantity": 1}],
    }), 400)
    ck(c.post("/api/invoices", json={
        "customer_id": cust, "payment_method": "partial", "paid": 100,
        "items": [{"product_id": p, "quantity": 1}],
    }), 400)
    credit_sale = ck(c.post("/api/invoices", json={
        "customer_id": cust, "payment_method": "credit",
        "items": [{"product_id": p, "quantity": 1}],
    })).json()
    ck(c.post("/api/invoices/return", json={
        "customer_id": cust, "original_invoice_id": credit_sale["id"],
        "items": [{"product_id": p, "quantity": 1}], "payment_method": "cash",
    }), 400)

    # Failure after business mutations but before commit must roll the whole invoice back.
    stock_before = ck(c.get(f"/api/products/{p}")).json()["stock"]
    inv_count_before = ck(c.get("/api/invoices?limit=500")).json()["total"]
    original_invoice_audit = invoice_routes.log_audit
    def fail_audit(*args, **kwargs):
        raise RuntimeError("injected audit failure")
    invoice_routes.log_audit = fail_audit
    try:
        ck(c.post("/api/invoices", json={
            "customer_id": cust, "payment_method": "cash",
            "items": [{"product_id": p, "quantity": 1}],
        }), 500)
    finally:
        invoice_routes.log_audit = original_invoice_audit
    stock_after = ck(c.get(f"/api/products/{p}")).json()["stock"]
    inv_count_after = ck(c.get("/api/invoices?limit=500")).json()["total"]
    assert stock_after == stock_before and inv_count_after == inv_count_before, (stock_before, stock_after, inv_count_before, inv_count_after)

    # Settings + audit are also one transaction.
    original_settings_audit = settings_routes.log_audit
    before_settings = ck(c.get("/api/settings")).json()
    settings_routes.log_audit = fail_audit
    try:
        ck(c.post("/api/settings", json={"store_name": "SHOULD_ROLLBACK"}), 500)
    finally:
        settings_routes.log_audit = original_settings_audit
    after_settings = ck(c.get("/api/settings")).json()
    assert after_settings.get("store_name") == before_settings.get("store_name"), (before_settings, after_settings)

print("HARDENING_VAT_ROLLBACK_PASS")
