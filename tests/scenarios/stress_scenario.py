import os,tempfile,pathlib,concurrent.futures
root=pathlib.Path(tempfile.mkdtemp(prefix='pos34stress_'))
os.environ['POS_DATABASE_URL']=f"sqlite:///{root/'test.db'}"; os.environ['POS_ADMIN_PASSWORD']='AdminPassword#12345'; os.environ['POS_JWT_SECRET']='z'*64; os.environ['POS_ALLOWED_HOSTS']='testserver'; os.environ['POS_ALLOWED_ORIGINS']='http://testserver'; os.environ['POS_RUNTIME_DIR']=str(root/'runtime')
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import Product, Invoice
with TestClient(app) as c:
    assert c.post('/api/auth/login',json={'login':'admin','password':'AdminPassword#12345'}).status_code==200
    pid=c.post('/api/products',json={'name':'Race','price':10,'cost':4,'stock':10}).json()['id']
    def sell(i):
        r=c.post('/api/invoices',json={'items':[{'product_id':pid,'quantity':1}],'payment_method':'cash'})
        return r.status_code, r.json() if r.headers.get('content-type','').startswith('application/json') else {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        out=list(ex.map(sell,range(20)))
    success=[x for x in out if x[0]==200]; rejected=[x for x in out if x[0] in (400,409)]
    db=SessionLocal(); p=db.query(Product).filter_by(id=pid).first(); invs=db.query(Invoice).filter(Invoice.type=='sale').all(); nums=[i.number for i in invs]; inos=[i.invoice_number for i in invs]; db.close()
    assert len(success)==10,(len(success),out)
    assert len(rejected)==10,(len(rejected),out)
    assert float(p.stock)==0.0 if False else True
    # p is detached but scalar loaded
    assert len(nums)==10 and len(set(nums))==10 and len(set(inos))==10,(nums,inos)
    db=SessionLocal(); stock=float(db.query(Product).filter_by(id=pid).first().stock); db.close(); assert stock==0.0,stock
print('STRESS_20_ON_10_PASS')
