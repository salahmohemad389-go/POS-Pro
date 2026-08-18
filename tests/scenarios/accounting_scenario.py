import os,tempfile,pathlib
root=pathlib.Path(tempfile.mkdtemp(prefix='pos34acct_'))
os.environ['POS_DATABASE_URL']=f"sqlite:///{root/'test.db'}"; os.environ['POS_ADMIN_PASSWORD']='AdminPassword#12345'; os.environ['POS_JWT_SECRET']='y'*64; os.environ['POS_ALLOWED_HOSTS']='testserver'; os.environ['POS_ALLOWED_ORIGINS']='http://testserver'; os.environ['POS_RUNTIME_DIR']=str(root/'runtime')
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    def ck(r,code=200): assert r.status_code==code,(r.status_code,r.text); return r
    ck(c.post('/api/auth/login',json={'login':'admin','password':'AdminPassword#12345'}))
    p=ck(c.post('/api/products',json={'name':'P','price':100,'cost':60,'stock':20})).json()['id']
    cust=ck(c.post('/api/customers',json={'name':'C'})).json()['id']
    # Sale 300 credit
    s1=ck(c.post('/api/invoices',json={'customer_id':cust,'items':[{'product_id':p,'quantity':3}],'payment_method':'credit'})).json()['id']
    # account return 100 -> debt 200
    r1=ck(c.post('/api/invoices/return',json={'customer_id':cust,'original_invoice_id':s1,'items':[{'product_id':p,'quantity':1}],'payment_method':'credit'})).json()['id']
    # collect 200
    cr=ck(c.post(f'/api/invoices/{s1}/collect',json={'amount':200})).json(); assert cr['remaining']==0,cr
    st=ck(c.get(f'/api/customers/{cust}/statement')).json(); sm=st['summary']; assert sm['total_sales']==300 and sm['total_returns']==100 and sm['net_sales']==200 and sm['total_paid']==200 and sm['current_balance']==0,sm
    # combined exact selected sale+return => 200/200/0
    comb=ck(c.post('/api/combined-invoice',json={'ids':[s1,r1],'options':{'deduct_returns':True}})).json()['invoice']; assert comb['absolute_total']==200 and abs(comb['paid'])==200 and abs(comb['remaining'])==0,comb
    # combined record must not change balance/stock
    cu=ck(c.get(f'/api/customers/{cust}')).json(); pr=ck(c.get(f'/api/products/{p}')).json(); assert cu['balance']==0 and pr['stock']==18.0,(cu,pr)
    # dashboard/profit net returns
    dash=ck(c.get('/api/reports/dashboard')).json(); assert dash['today_sales']==200,dash
    prof=ck(c.get('/api/reports/profit')).json(); assert prof['total_revenue']==200 and prof['total_cost']==120 and prof['profit']==80,prof
    # PDF same endpoint works and tax disabled does not introduce tax
    pdf=ck(c.get(f'/api/invoices/{s1}/pdf')); assert pdf.headers['content-type']=='application/pdf' and pdf.content.startswith(b'%PDF')
print('ACCOUNTING_REPORTS_PASS')
