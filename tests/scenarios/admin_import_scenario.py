import concurrent.futures
import os
import pathlib
import tempfile

root = pathlib.Path(tempfile.mkdtemp(prefix='pos34admin_'))
os.environ['POS_DATABASE_URL'] = f"sqlite:///{root/'test.db'}"
os.environ['POS_ADMIN_PASSWORD'] = 'AdminPassword#12345'
os.environ['POS_JWT_SECRET'] = 'a' * 64
os.environ['POS_ALLOWED_HOSTS'] = 'testserver'
os.environ['POS_ALLOWED_ORIGINS'] = 'http://testserver'
os.environ['POS_RUNTIME_DIR'] = str(root/'runtime')

from fastapi.testclient import TestClient
from app.main import app
from app.core.ratelimit import consume_attempt
from app.db.models import Customer, CustomerLedger, Product, User
from app.db.session import SessionLocal


def expect(resp, code=200, label=''):
    assert resp.status_code == code, f"{label}: {resp.status_code} {resp.text}"
    return resp

with TestClient(app) as c:
    admin = expect(c.post('/api/auth/login', json={'login':'admin','password':'AdminPassword#12345'}), label='admin login').json()['user']
    admin_id = admin['id']

    # Last active admin cannot demote self.
    expect(c.post('/api/users', json={'id':admin_id,'name':'المدير','login':'admin','role':'manager','password':''}), 409, 'last admin demotion')

    manager_id = expect(c.post('/api/users', json={'name':'Manager','login':'mgr','role':'manager','password':'ManagerPassword#123'}), label='manager create').json()['id']
    cashier_id = expect(c.post('/api/users', json={'name':'Cashier','login':'cash','role':'cashier','password':'CashierPassword#123'}), label='cashier create').json()['id']

    # Category-name resolution in product import + strict numeric parsing.
    cat_id = expect(c.post('/api/categories', json={'name':'Imported Category'}), label='category').json()['id']
    bad_csv = b'Name,Price,Stock\nBad,not-a-number,1\n'
    r = expect(c.post('/api/products/import', files={'file':('bad.csv', bad_csv, 'text/csv')}), label='bad numeric import').json()
    assert r['added'] == 0 and r['total_errors'] == 1, r

    good_csv = 'Name,Barcode,Price,Cost,Stock,Min Stock,Category\nImported,IMP-1,10,5,1.005,0.005,Imported Category\n'.encode()
    r = expect(c.post('/api/products/import', files={'file':('good.csv', good_csv, 'text/csv')}), label='good import').json()
    assert r['added'] == 1, r
    found = expect(c.post('/api/products/find', json={'q':'IMP-1'}), label='find import').json()['exact']
    assert found['stock'] == 1.005 and found['min_stock'] == 0.005 and found['category_id'] == cat_id, found

    # CSV export must neutralize spreadsheet formulas.
    expect(c.post('/api/products', json={'name':'=CMD()', 'code':'FORMULA', 'price':1, 'stock':1}), label='formula product')
    exported = expect(c.get('/api/products/export?format=csv'), label='formula export')
    text = exported.content.decode('utf-8-sig')
    assert "'=CMD()" in text, text

    # Customer import creates an opening-balance ledger; malformed numeric balance is rejected per row.
    cust_csv = 'Name,Phone,Balance\nImported Customer,0100,25.50\nBad Balance,,abc\n'.encode()
    ir = expect(c.post('/api/customers/import', files={'file':('customers.csv', cust_csv, 'text/csv')}), label='customer import').json()
    assert ir['added'] == 1 and ir['total_errors'] == 1, ir
    db = SessionLocal()
    cust = db.query(Customer).filter(Customer.name == 'Imported Customer').first()
    assert cust is not None and float(cust.balance) == 25.5
    assert db.query(CustomerLedger).filter(CustomerLedger.customer_id == cust.id, CustomerLedger.movement_type == 'opening').count() == 1
    imported_cust_id = cust.id
    db.close()
    expect(c.delete(f'/api/customers/{imported_cust_id}'), 409, 'customer ledger delete block')

    # Backup path validation and actual local backup/download.
    expect(c.post('/api/backup/restore', json={'name':'../backup_evil.zip'}), 422, 'restore traversal')
    backup = expect(c.post('/api/backup', json={}), label='backup create').json()['name']
    z = expect(c.get(f'/api/backup/download/{backup}'), label='backup download')
    assert z.content.startswith(b'PK'), z.content[:10]

    # Manager can inspect users/audit but cannot mutate settings/users/clear audit.
    expect(c.post('/api/auth/logout'))
    expect(c.post('/api/auth/login', json={'login':'mgr','password':'ManagerPassword#123'}), label='manager login')
    expect(c.get('/api/users'), 200, 'manager users view')
    expect(c.get('/api/audit'), 200, 'manager audit view')
    expect(c.post('/api/settings', json={'store_name':'Nope'}), 403, 'manager settings')
    expect(c.post('/api/users', json={'name':'X','login':'x','role':'cashier','password':'PasswordForUser#123'}), 403, 'manager user save')
    expect(c.delete('/api/audit'), 403, 'manager audit clear')

    # Cashier has only operational views; sensitive lists remain closed.
    expect(c.post('/api/auth/logout'))
    expect(c.post('/api/auth/login', json={'login':'cash','password':'CashierPassword#123'}), label='cashier login')
    expect(c.get('/api/users'), 403, 'cashier users')
    expect(c.get('/api/suppliers'), 403, 'cashier suppliers')
    expect(c.get('/api/reports/customer-debts'), 403, 'cashier debts')
    expect(c.get('/api/reports/low-stock'), 200, 'cashier low stock')

# File limiter must be atomic under threads: five allowed, sixth+ denied.
key = 'atomic-test-key'
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
    results = list(ex.map(lambda _i: consume_attempt(key, 'login')[0], range(20)))
assert sum(results) == 5, results
print('ADMIN_IMPORT_PERMISSIONS_PASS')
