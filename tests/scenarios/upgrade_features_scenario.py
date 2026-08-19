import os
import pathlib
import tempfile
from datetime import datetime, timedelta, timezone

root = pathlib.Path(tempfile.mkdtemp(prefix='pos34upgrade_'))
os.environ['POS_DATABASE_URL'] = f"sqlite:///{root/'test.db'}"
os.environ['POS_ADMIN_PASSWORD'] = 'AdminPassword#12345'
os.environ['POS_JWT_SECRET'] = 'u' * 64
os.environ['POS_ALLOWED_HOSTS'] = 'testserver'
os.environ['POS_ALLOWED_ORIGINS'] = 'http://testserver'
os.environ['POS_RUNTIME_DIR'] = str(root/'runtime')

from fastapi.testclient import TestClient
from app.main import app

def ok(resp, code=200):
    assert resp.status_code == code, (resp.status_code, resp.text)
    return resp

with TestClient(app) as owner:
    brand = ok(owner.get('/api/branding')).json()
    assert brand['store_name'] == 'صالح الأسناوي' and 'logo' in brand
    owner_user = ok(owner.post('/api/auth/login', json={'login':'admin','password':'AdminPassword#12345'})).json()['user']
    assert owner_user['is_owner'] is True
    pid = ok(owner.post('/api/products', json={'name':'Merged P','barcode':'MRG-P','price':100,'cost':50,'stock':20})).json()['id']
    cid = ok(owner.post('/api/customers', json={'name':'Merged C'})).json()['id']
    s1 = ok(owner.post('/api/invoices', json={'customer_id':cid,'items':[{'product_id':pid,'quantity':5}],'payment_method':'cash'})).json()['id']
    s2 = ok(owner.post('/api/invoices', json={'customer_id':cid,'items':[{'product_id':pid,'quantity':4}],'payment_method':'cash'})).json()['id']
    ok(owner.post('/api/invoices/return', json={'customer_id':cid,'original_invoice_id':s1,'items':[{'product_id':pid,'quantity':2}],'payment_method':'cash'}))
    combined = ok(owner.post('/api/combined-invoice', json={'ids':[s1,s2],'options':{'deduct_returns':True}})).json()['invoice']
    assert len(combined['items']) == 1 and float(combined['items'][0]['quantity']) == 7.0, combined
    assert float(combined['total']) == 700.0, combined
    product = ok(owner.get(f'/api/products/{pid}')).json(); assert float(product['stock']) == 13.0, product
    csv = 'Barcode,Price\nMRG-P,150\nUNKNOWN,999\n'.encode()
    upd = ok(owner.post('/api/products/import-prices', files={'file':('prices.csv', csv, 'text/csv')})).json()
    assert upd['updated'] == 1 and upd['not_found'] == 1, upd
    product = ok(owner.get(f'/api/products/{pid}')).json(); assert float(product['price']) == 150.0
    all_products = ok(owner.get('/api/products?limit=500')).json()['items']
    assert sum(1 for p in all_products if p['barcode'] == 'MRG-P') == 1
    assert not any(p.get('barcode') == 'UNKNOWN' for p in all_products)
    ok(owner.post('/api/settings', json={'store_name':'اختبار العلامة','feature_reports_enabled':False,'feature_suppliers_enabled':False}))
    settings = ok(owner.get('/api/settings')).json(); assert settings['feature_reports_enabled'] is False and settings['feature_suppliers_enabled'] is False
    assert ok(owner.get('/api/branding')).json()['store_name'] == 'اختبار العلامة'
    ok(owner.post('/api/users', json={'name':'Limited Manager','login':'limitedmgr','role':'manager','password':'ManagerPassword#123','permissions':['user_view']}))
    with TestClient(app) as mgr:
        ok(mgr.post('/api/auth/login', json={'login':'limitedmgr','password':'ManagerPassword#123'})); users = ok(mgr.get('/api/users')).json()
        assert all(not u.get('is_owner') for u in users); assert all(u['id'] != owner_user['id'] for u in users); ok(mgr.get('/api/products'), 403)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    ok(owner.post('/api/users', json={'name':'Expired','login':'expired','role':'cashier','password':'CashierPassword#123','expires_at':past}))
    with TestClient(app) as expired: ok(expired.post('/api/auth/login', json={'login':'expired','password':'CashierPassword#123'}), 403)
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    kick_id = ok(owner.post('/api/users', json={'name':'Kick Me','login':'kickme','role':'cashier','password':'CashierPassword#123','expires_at':future})).json()['id']
    with TestClient(app) as worker:
        ok(worker.post('/api/auth/login', json={'login':'kickme','password':'CashierPassword#123'})); ok(worker.get('/api/auth/me')); ok(owner.post(f'/api/users/{kick_id}/revoke-sessions', json={})); ok(worker.get('/api/auth/me'), 401)
print('UPGRADE_FEATURES_PASS')
