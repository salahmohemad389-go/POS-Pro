import os, tempfile, pathlib
root=pathlib.Path(tempfile.mkdtemp(prefix='pos34_'))
os.environ['POS_DATABASE_URL']=f"sqlite:///{root/'test.db'}"
os.environ['POS_ADMIN_PASSWORD']='AdminPassword#12345'
os.environ['POS_JWT_SECRET']='x'*64
os.environ['POS_ALLOWED_HOSTS']='testserver,localhost,127.0.0.1'
os.environ['POS_ALLOWED_ORIGINS']='http://testserver'
os.environ['POS_RUNTIME_DIR']=str(root/'runtime')
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import User, Product, Customer, Invoice
from app.core.security import hash_password

with TestClient(app) as c:
    h=c.get('/api/health'); assert h.status_code==200 and h.json()['ok'] is True, h.text
    def ok(resp, code=200, label=''):
        assert resp.status_code==code, f"{label} {resp.status_code}: {resp.text}"
        return resp
    r=ok(c.post('/api/auth/login',json={'login':'admin','password':'AdminPassword#12345'}),label='login')
    # Settings strict validation
    ok(c.post('/api/settings',json={'vat_enabled':'false'}),422,'strict bool')
    ok(c.post('/api/settings',json={'copies':-5}),422,'copies')
    ok(c.post('/api/settings',json={'invoice_format':'garbage'}),422,'format')
    ok(c.post('/api/settings',json={'logo':'data:text/html;base64,PHNjcmlwdD4='}),422,'logo')
    ok(c.post('/api/settings',json={'vat_enabled':False,'tax_rate':14,'copies':1,'invoice_format':'a4'}),label='settings valid')
    # Products nonnegative and precision
    ok(c.post('/api/products',json={'name':'bad','price':-1}),422,'negative product')
    pid=ok(c.post('/api/products',json={'name':'P','barcode':'111','price':50,'cost':20,'stock':10.005,'min_stock':1.005}),label='product').json()['id']
    prod=ok(c.get(f'/api/products/{pid}'),label='product get').json()
    assert prod['stock']==10.005 and prod['min_stock']==1.005, prod
    # Customer export route is not swallowed by /{cid}
    er=ok(c.get('/api/customers/export?format=csv'),label='cust export')
    assert 'text/csv' in er.headers.get('content-type','')
    # Category self-parent blocked
    cid=ok(c.post('/api/categories',json={'name':'Root'}),label='cat').json()['id']
    ok(c.post('/api/categories',json={'id':cid,'name':'Root','parent_id':cid}),400,'self parent')
    # Customer + credit sale
    cust=ok(c.post('/api/customers',json={'name':'Customer A'}),label='customer').json()['id']
    sale=ok(c.post('/api/invoices',json={'customer_id':cust,'items':[{'product_id':pid,'quantity':2}], 'paid':0,'payment_method':'credit'}),label='credit sale').json()
    sale_id=sale['id']
    # Duplicate item sale cannot oversell available stock
    ok(c.post('/api/invoices',json={'items':[{'product_id':pid,'quantity':5},{'product_id':pid,'quantity':5}], 'paid':500}),400,'duplicate oversell')
    # credit return defaults requested cash but must not invent cash; paid must be zero
    rr=ok(c.post('/api/invoices/return',json={'customer_id':cust,'original_invoice_id':sale_id,'items':[{'product_id':pid,'quantity':1}], 'payment_method':'credit'}),label='credit return').json()
    assert rr['paid']==0.0 and rr['remaining']==50.0, rr
    # crafted duplicate return cannot exceed sold qty (one already returned, only one left)
    ok(c.post('/api/invoices/return',json={'customer_id':cust,'original_invoice_id':sale_id,'items':[{'product_id':pid,'quantity':0.6},{'product_id':pid,'quantity':0.6}], 'payment_method':'credit'}),400,'duplicate return')
    # no cash may be refunded from a fully-credit source sale
    ok(c.post('/api/invoices/return',json={'customer_id':cust,'original_invoice_id':sale_id,'items':[{'product_id':pid,'quantity':1}], 'payment_method':'cash','paid':50}),400,'cash refund cap')
    # Client cannot inject calculated invoice totals/tax fields; server owns the calculation.
    ok(c.post('/api/invoices',json={'items':[{'product_id':pid,'quantity':1}],'payment_method':'cash','total':1}),422,'server authoritative totals')
    # Combined options are strict booleans, not truthy strings.
    ok(c.post('/api/combined-invoice',json={'ids':[sale_id,rr['id']],'options':{'deduct_returns':'false'}}),422,'combined strict bool')
    # create second cashier and foreign invoice IDOR checks
    db=SessionLocal(); u=User(name='Cash2',login='cash2',role='cashier',active=True,password_hash=hash_password('CashierPassword#123')); db.add(u); db.commit(); db.refresh(u); cash2=u.id; db.close()
    # admin creates sale means user_id admin; cashier cannot read return-items/collect/return
    c.post('/api/auth/logout')
    ok(c.post('/api/auth/login',json={'login':'cash2','password':'CashierPassword#123'}),label='cash login')
    ok(c.get(f'/api/invoices/return-original-items/{sale_id}'),403,'idor return read')
    ok(c.post(f'/api/invoices/{sale_id}/collect',json={'amount':10}),403,'idor collect')
    ok(c.post('/api/invoices/return',json={'customer_id':cust,'original_invoice_id':sale_id,'items':[{'product_id':pid,'quantity':1}],'payment_method':'credit'}),403,'idor return create')
    ok(c.get(f'/api/customers/{cust}/statement'),403,'cashier statement')
    ok(c.post(f'/api/customers/{cust}/collect',json={'amount':10}),403,'cashier customer collect')
print('RELEASE_SCENARIOS_PASS')
