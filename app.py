from flask import Flask, jsonify, request, session, render_template
from dotenv import load_dotenv
load_dotenv()
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from functools import wraps
import os, secrets, sqlite3, re, smtplib
from contextlib import contextmanager
from email.message import EmailMessage

app=Flask(__name__)
app.config['SECRET_KEY']=os.environ.get('RMR_SECRET_KEY','local-rentmyride-change-this-key')
DB=os.path.join(app.root_path,'rentmyride.db')

@contextmanager
def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    try:
        yield c
        c.commit()
    except:
        c.rollback()
        raise
    finally:
        c.close()
def now(): return datetime.now().isoformat(timespec='seconds')
def init_db():
    with conn() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,contact TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'customer',status TEXT NOT NULL DEFAULT 'Active',created_at TEXT);
        CREATE TABLE IF NOT EXISTS providers(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER UNIQUE,business_name TEXT,phone TEXT,address TEXT,document_name TEXT,status TEXT DEFAULT 'Pending',created_at TEXT);
        CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY AUTOINCREMENT,provider_id INTEGER,vehicle_type TEXT,model TEXT,registration_number TEXT UNIQUE,location TEXT,rent_per_day REAL,description TEXT,status TEXT DEFAULT 'Pending',created_at TEXT,quantity INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY AUTOINCREMENT,vehicle_id INTEGER,customer_id INTEGER,start_date TEXT,end_date TEXT,days INTEGER,total_amount REAL,status TEXT DEFAULT 'Pending',created_at TEXT,quantity INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,booking_id INTEGER,customer_id INTEGER,amount REAL,method TEXT,status TEXT,transaction_ref TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS complaints(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,subject TEXT,message TEXT,status TEXT DEFAULT 'Open',response TEXT DEFAULT '',created_at TEXT);
        CREATE TABLE IF NOT EXISTS otps(contact TEXT PRIMARY KEY,code TEXT,expires_at TEXT,verified INTEGER DEFAULT 0,purpose TEXT);''')
        # Backward-compatible migration for existing local databases.
        vehicle_cols={r['name'] for r in c.execute('PRAGMA table_info(vehicles)').fetchall()}
        if 'quantity' not in vehicle_cols:c.execute('ALTER TABLE vehicles ADD COLUMN quantity INTEGER DEFAULT 1')
        booking_cols={r['name'] for r in c.execute('PRAGMA table_info(bookings)').fetchall()}
        if 'quantity' not in booking_cols:c.execute('ALTER TABLE bookings ADD COLUMN quantity INTEGER DEFAULT 1')
        admin=c.execute('SELECT id FROM users WHERE contact=?',('admin@rentmyride.com',)).fetchone()
        if not admin:c.execute('INSERT INTO users(name,contact,password_hash,role,status,created_at) VALUES(?,?,?,?,?,?)',('RentMyRide Admin','admin@rentmyride.com',generate_password_hash('Admin@123'),'admin','Active',now()))
init_db()
def get_user(uid):
    if not uid:return None
    with conn() as c:return c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
def user_dict(u):return dict(id=u['id'],name=u['name'],contact=u['contact'],role=u['role'],status=u['status'],created_at=u['created_at'])
def current_user():return get_user(session.get('uid'))
def require_role(*roles):
    def deco(fn):
        @wraps(fn)
        def wrap(*a,**kw):
            u=current_user()
            if not u:return jsonify(error='Please log in.'),401
            if roles and u['role'] not in roles:return jsonify(error='Access denied.'),403
            return fn(*a,**kw)
        return wrap
    return deco
def get_provider_by_user(uid):
    with conn() as c:return c.execute('SELECT * FROM providers WHERE user_id=?',(uid,)).fetchone()
def vehicle_available(vehicle_id,total,start_date,end_date):
    with conn() as c:
        rows=c.execute("SELECT quantity FROM bookings WHERE vehicle_id=? AND status IN ('Pending','Confirmed','Paid') AND start_date<? AND end_date>?",(vehicle_id,end_date,start_date)).fetchall()
    reserved=sum(int(r['quantity'] or 1) for r in rows)
    return max(0,int(total or 1)-reserved)
def vehicle_dict(v):
    with conn() as c:p=c.execute('SELECT business_name FROM providers WHERE id=?',(v['provider_id'],)).fetchone()
    total=int(v['quantity'] or 1);today=date.today();available=vehicle_available(v['id'],total,today.isoformat(),(today+timedelta(days=1)).isoformat())
    return dict(id=v['id'],provider_id=v['provider_id'],provider_name=p['business_name'] if p else 'Provider',type=v['vehicle_type'],model=v['model'],registration_number=v['registration_number'] or '',location=v['location'],rent_per_day=v['rent_per_day'],description=v['description'],status=v['status'],quantity=total,available_quantity=available,reserved_quantity=total-available)
def booking_dict(b):
    with conn() as c:
        v=c.execute('SELECT * FROM vehicles WHERE id=?',(b['vehicle_id'],)).fetchone();u=c.execute('SELECT * FROM users WHERE id=?',(b['customer_id'],)).fetchone()
    return dict(id=b['id'],vehicle=vehicle_dict(v) if v else None,customer=user_dict(u) if u else None,start_date=b['start_date'],end_date=b['end_date'],days=b['days'],quantity=int(b['quantity'] or 1),total_amount=b['total_amount'],status=b['status'],created_at=b['created_at'])
def valid_email(x):return bool(re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',x or ''))
def valid_phone(x):return bool(re.fullmatch(r'[6-9]\d{9}',x or ''))
def valid_password(x):return bool(len(x)>=8 and re.search(r'[A-Z]',x) and re.search(r'[a-z]',x) and re.search(r'\d',x) and re.search(r'[^A-Za-z0-9]',x))
def send_otp(email,code):
    host=os.environ.get('RMR_SMTP_HOST'); port=int(os.environ.get('RMR_SMTP_PORT','587')); sender=os.environ.get('RMR_SMTP_EMAIL'); pwd=os.environ.get('RMR_SMTP_PASSWORD')
    if host and sender and pwd:
        msg=EmailMessage();msg['Subject']='RentMyRide verification code';msg['From']=sender;msg['To']=email;msg.set_content(f'Your RentMyRide OTP is {code}. It expires in 2 minutes.')
        with smtplib.SMTP(host,port,timeout=15) as s:s.starttls();s.login(sender,pwd);s.send_message(msg)
        return False
    return True # local demo: show OTP in response for testing
@app.get('/')
def home():return render_template('app.html')
@app.get('/health')
def health():return jsonify(status='ok',app='RentMyRide')
@app.get('/api/me')
def me():u=current_user();return jsonify(user=user_dict(u) if u else None)
@app.post('/api/otp/send')
def otp_send():
    d=request.get_json(silent=True) or {}; email=(d.get('contact') or '').strip().lower();purpose=d.get('purpose','signup')
    if not valid_email(email):return jsonify(error='Enter a valid email address.'),400
    with conn() as c:
        existing=c.execute('SELECT * FROM users WHERE contact=?',(email,)).fetchone()
        if purpose=='signup' and existing:return jsonify(error='Email already registered. Please log in.'),409
        if purpose=='reset' and not existing:return jsonify(error='No account found with this email.'),404
        previous=c.execute('SELECT expires_at,verified FROM otps WHERE contact=? AND purpose=?',(email,purpose)).fetchone()
        if previous and not previous['verified'] and float(previous['expires_at'])>datetime.now().timestamp():
            remaining=max(1,int(float(previous['expires_at'])-datetime.now().timestamp()))
            return jsonify(error=f'OTP already sent. Please wait {remaining} seconds before requesting another.'),429
    code=f'{secrets.randbelow(1000000):06d}'; expires=(datetime.now().timestamp()+120)
    demo=send_otp(email,code)
    with conn() as c:c.execute('INSERT OR REPLACE INTO otps(contact,code,expires_at,verified,purpose) VALUES(?,?,?,?,?)',(email,code,str(expires),0,purpose))
    result={'message':'OTP sent to your email. Valid for 2 minutes.'}
    if demo:result['demo_otp']=code;result['message']='Email sending is not configured; local testing OTP is shown below.'
    return jsonify(result)
@app.post('/api/otp/verify')
def otp_verify():
    d=request.get_json(silent=True) or {}; email=(d.get('contact') or '').strip().lower();code=(d.get('otp') or '').strip();purpose=d.get('purpose','signup')
    with conn() as c:r=c.execute('SELECT * FROM otps WHERE contact=? AND purpose=?',(email,purpose)).fetchone()
    if not r or r['code']!=code or float(r['expires_at'])<datetime.now().timestamp():return jsonify(error='Invalid or expired OTP. Please request a new one.'),400
    with conn() as c:c.execute('UPDATE otps SET verified=1 WHERE contact=? AND purpose=?',(email,purpose))
    return jsonify(ok=True,message='Email verified successfully.')
@app.post('/api/signup')
def signup():
    d=request.get_json(silent=True) or {};email=(d.get('contact') or '').strip().lower();name=(d.get('name') or '').strip();pw=d.get('password') or ''
    with conn() as c:o=c.execute('SELECT verified,expires_at FROM otps WHERE contact=? AND purpose=?',(email,'signup')).fetchone()
    if not valid_email(email) or not name or not valid_password(pw):return jsonify(error='Enter name, valid email, and a strong password (8+ chars, uppercase, lowercase, number and special character).'),400
    if not o or not o['verified'] or float(o['expires_at'])<datetime.now().timestamp():return jsonify(error='Verify your email OTP before creating the account.'),403
    with conn() as c:
        if c.execute('SELECT id FROM users WHERE contact=?',(email,)).fetchone():return jsonify(error='Account already exists. Log in instead.'),409
        c.execute('INSERT INTO users(name,contact,password_hash,role,status,created_at) VALUES(?,?,?,?,?,?)',(name,email,generate_password_hash(pw),'customer','Active',now()));u=c.execute('SELECT * FROM users WHERE contact=?',(email,)).fetchone();c.execute('DELETE FROM otps WHERE contact=?',(email,))
    session['uid']=u['id'];return jsonify(user=user_dict(u)),201
@app.post('/api/login')
def login():
    d=request.get_json(silent=True) or {};contact=(d.get('contact') or '').strip().lower();pw=d.get('password') or ''
    with conn() as c:u=c.execute('SELECT * FROM users WHERE contact=?',(contact,)).fetchone()
    if not u or not check_password_hash(u['password_hash'],pw):return jsonify(error='Invalid email or password.'),401
    if u['status']=='Blocked':return jsonify(error='This account is blocked. Contact admin.'),403
    session['uid']=u['id'];return jsonify(user=user_dict(u))
@app.post('/api/admin/login')
def admin_login():
    d=request.get_json(silent=True) or {}
    if d.get('contact')!='admin@rentmyride.com' or d.get('password')!='Admin@123':return jsonify(error='Invalid admin credentials.'),401
    with conn() as c:u=c.execute('SELECT * FROM users WHERE contact=?',('admin@rentmyride.com',)).fetchone()
    session['uid']=u['id'];return jsonify(user=user_dict(u))
@app.post('/api/logout')
def logout():session.clear();return jsonify(ok=True)
@app.post('/api/password-reset')
def password_reset():
    d=request.get_json(silent=True) or {};email=(d.get('contact') or '').strip().lower();pw=d.get('new_password') or ''
    with conn() as c:o=c.execute('SELECT verified,expires_at FROM otps WHERE contact=? AND purpose=?',(email,'reset')).fetchone();u=c.execute('SELECT id FROM users WHERE contact=?',(email,)).fetchone()
    if not o or not o['verified'] or float(o['expires_at'])<datetime.now().timestamp():return jsonify(error='Verify reset OTP first.'),403
    if not u:return jsonify(error='Account not found.'),404
    if not valid_password(pw):return jsonify(error='Password must be 8+ characters with uppercase, lowercase, number and special character.'),400
    with conn() as c:c.execute('UPDATE users SET password_hash=? WHERE contact=?',(generate_password_hash(pw),email));c.execute('DELETE FROM otps WHERE contact=?',(email,))
    return jsonify(ok=True,message='Password reset successfully. Please login.')
@app.post('/api/provider/apply')
@require_role('customer','provider')
def provider_apply():
    u=current_user();d=request.get_json(silent=True) or {};business=(d.get('business_name') or '').strip();phone=(d.get('phone') or '').strip();address=(d.get('address') or '').strip()
    if not business:return jsonify(error='Provider/business name is required.'),400
    if not valid_phone(phone):return jsonify(error='Enter a valid 10-digit Indian mobile number.'),400
    if not address:return jsonify(error='Address is required. Type it or use current location.'),400
    with conn() as c:
        if c.execute('SELECT id FROM providers WHERE user_id=?',(u['id'],)).fetchone():return jsonify(error='Provider application already submitted.'),409
        c.execute('INSERT INTO providers(user_id,business_name,phone,address,document_name,status,created_at) VALUES(?,?,?,?,?,?,?)',(u['id'],business,phone,address,(d.get('document_name') or '').strip(),'Pending',now()));c.execute('UPDATE users SET role=? WHERE id=?',('provider',u['id']))
    return jsonify(status='Pending',message='Application submitted for admin approval.'),201
@app.get('/api/provider/me')
@require_role('provider')
def provider_me():p=get_provider_by_user(current_user()['id']);return jsonify(provider={'id':p['id'],'business_name':p['business_name'],'status':p['status']} if p else None)
@app.post('/api/vehicles')
@require_role('provider')
def add_vehicle():
    p=get_provider_by_user(current_user()['id']);d=request.get_json(silent=True) or {}
    if not p or p['status']!='Approved':return jsonify(error='Provider account must be approved before adding vehicles.'),403
    model=(d.get('model') or '').strip();reg=(d.get('registration_number') or '').strip().upper() or None;loc=(d.get('location') or '').strip();typ=d.get('type','Car');desc=(d.get('description') or '').strip()
    try:rent=float(d.get('rent_per_day'))
    except:return jsonify(error='Enter a valid rental price.'),400
    try:quantity=int(d.get('quantity',1))
    except:return jsonify(error='Enter a valid vehicle quantity.'),400
    if not model or not loc:return jsonify(error='Model and location are required.'),400
    if reg and not re.fullmatch(r'[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}',reg):return jsonify(error='Enter a valid vehicle registration format (example: TN01AB1234).'),400
    if rent<=0:return jsonify(error='Daily rental price must be greater than zero.'),400
    if quantity<1 or quantity>500:return jsonify(error='Quantity must be between 1 and 500.'),400
    if typ not in ['Car','Bike','Scooter','Van']:return jsonify(error='Select a valid vehicle type.'),400
    with conn() as c:
        if reg and c.execute('SELECT id FROM vehicles WHERE registration_number=?',(reg,)).fetchone():return jsonify(error='Registration number already exists.'),409
        c.execute('INSERT INTO vehicles(provider_id,vehicle_type,model,registration_number,location,rent_per_day,description,status,created_at,quantity) VALUES(?,?,?,?,?,?,?,?,?,?)',(p['id'],typ,model,reg,loc,rent,desc,'Pending',now(),quantity));v=c.execute('SELECT * FROM vehicles ORDER BY id DESC LIMIT 1').fetchone()
    return jsonify(vehicle=vehicle_dict(v),message='Vehicle quantity submitted for approval.'),201
@app.get('/api/provider/vehicles')
@require_role('provider')
def provider_vehicles():
    p=get_provider_by_user(current_user()['id'])
    with conn() as c:rows=c.execute('SELECT * FROM vehicles WHERE provider_id=?',(p['id'],)).fetchall() if p else []
    return jsonify(vehicles=[vehicle_dict(x) for x in rows])
@app.get('/api/vehicles')
def vehicles():
    loc=(request.args.get('location') or '').lower();typ=request.args.get('type') or '';maxp=request.args.get('max_price')
    with conn() as c:rows=c.execute("SELECT * FROM vehicles WHERE status='Approved'").fetchall()
    items=[vehicle_dict(x) for x in rows];items=[x for x in items if (not loc or loc in x['location'].lower()) and (not typ or typ==x['type'])]
    if maxp:
        try:items=[x for x in items if x['rent_per_day']<=float(maxp)]
        except:pass
    return jsonify(vehicles=items)
@app.post('/api/bookings')
@require_role('customer')
def create_booking():
    d=request.get_json(silent=True) or {}
    with conn() as c:v=c.execute('SELECT * FROM vehicles WHERE id=?',(d.get('vehicle_id'),)).fetchone()
    if not v or v['status']!='Approved':return jsonify(error='Vehicle is unavailable.'),404
    try:s=date.fromisoformat(d['start_date']);e=date.fromisoformat(d['end_date']);days=(e-s).days;quantity=int(d.get('quantity',1))
    except:return jsonify(error='Enter valid booking dates and quantity.'),400
    if days<1:return jsonify(error='End date must be after start date.'),400
    if quantity<1:return jsonify(error='Select at least one vehicle.'),400
    available=vehicle_available(v['id'],int(v['quantity'] or 1),s.isoformat(),e.isoformat())
    if quantity>available:return jsonify(error=f'Only {available} vehicle(s) available for those dates.'),409
    with conn() as c:
        c.execute('INSERT INTO bookings(vehicle_id,customer_id,start_date,end_date,days,total_amount,status,created_at,quantity) VALUES(?,?,?,?,?,?,?,?,?)',(v['id'],current_user()['id'],s.isoformat(),e.isoformat(),days,days*v['rent_per_day']*quantity,'Pending',now(),quantity));b=c.execute('SELECT * FROM bookings ORDER BY id DESC LIMIT 1').fetchone()
    return jsonify(booking=booking_dict(b)),201
@app.get('/api/bookings')
@require_role('customer','provider','admin')
def list_bookings():
    u=current_user()
    with conn() as c:
        if u['role']=='customer':rows=c.execute('SELECT * FROM bookings WHERE customer_id=?',(u['id'],)).fetchall()
        elif u['role']=='provider':
            p=get_provider_by_user(u['id']);rows=c.execute('SELECT b.* FROM bookings b JOIN vehicles v ON v.id=b.vehicle_id WHERE v.provider_id=?',(p['id'],)).fetchall() if p else []
        else:rows=c.execute('SELECT * FROM bookings').fetchall()
    return jsonify(bookings=[booking_dict(b) for b in rows])
@app.post('/api/bookings/<int:bid>/confirm')
@require_role('provider','admin')
def confirm_booking(bid):
    with conn() as c:b=c.execute('SELECT * FROM bookings WHERE id=?',(bid,)).fetchone()
    if not b:return jsonify(error='Booking not found.'),404
    u=current_user()
    if u['role']=='provider':
        p=get_provider_by_user(u['id'])
        with conn() as c:v=c.execute('SELECT provider_id FROM vehicles WHERE id=?',(b['vehicle_id'],)).fetchone()
        if not p or v['provider_id']!=p['id']:return jsonify(error='Access denied.'),403
    with conn() as c:c.execute('UPDATE bookings SET status=? WHERE id=?',('Confirmed',bid));b=c.execute('SELECT * FROM bookings WHERE id=?',(bid,)).fetchone()
    return jsonify(booking=booking_dict(b))
@app.post('/api/bookings/<int:bid>/cancel')
@require_role('customer','provider','admin')
def cancel_booking(bid):
    u=current_user()
    with conn() as c:b=c.execute('SELECT * FROM bookings WHERE id=?',(bid,)).fetchone()
    if not b:return jsonify(error='Booking not found.'),404
    if u['role']=='customer' and b['customer_id']!=u['id']:return jsonify(error='Access denied.'),403
    with conn() as c:c.execute('UPDATE bookings SET status=? WHERE id=?',('Cancelled',bid));b=c.execute('SELECT * FROM bookings WHERE id=?',(bid,)).fetchone()
    return jsonify(booking=booking_dict(b))
@app.post('/api/bookings/<int:bid>/pay')
@require_role('customer')
def pay(bid):
    u=current_user()
    with conn() as c:b=c.execute('SELECT * FROM bookings WHERE id=?',(bid,)).fetchone()
    if not b:return jsonify(error='Booking not found.'),404
    if b['customer_id']!=u['id']:return jsonify(error='Access denied.'),403
    if b['status'] not in ['Confirmed','Pending']:return jsonify(error='Booking cannot be paid.'),400
    ref='DEMO-'+secrets.token_hex(5).upper()
    with conn() as c:c.execute('INSERT INTO payments(booking_id,customer_id,amount,method,status,transaction_ref,created_at) VALUES(?,?,?,?,?,?,?)',(bid,u['id'],b['total_amount'],'Demo gateway','Paid',ref,now()));c.execute('UPDATE bookings SET status=? WHERE id=?',('Paid',bid));b=c.execute('SELECT * FROM bookings WHERE id=?',(bid,)).fetchone()
    return jsonify(payment={'amount':b['total_amount'],'status':'Paid','transaction_ref':ref},booking=booking_dict(b),notice='DEMO PAYMENT ONLY - no money was charged.')
@app.post('/api/complaints')
@require_role('customer','provider')
def create_complaint():
    d=request.get_json(silent=True) or {};subject=(d.get('subject') or '').strip();msg=(d.get('message') or '').strip()
    if not subject or not msg:return jsonify(error='Subject and message required.'),400
    with conn() as c:c.execute('INSERT INTO complaints(user_id,subject,message,status,response,created_at) VALUES(?,?,?,?,?,?)',(current_user()['id'],subject,msg,'Open','',now()));r=c.execute('SELECT * FROM complaints ORDER BY id DESC LIMIT 1').fetchone()
    return jsonify(complaint={'id':r['id'],'status':r['status']}),201
@app.get('/api/complaints')
@require_role('customer','provider','admin')
def complaints():
    u=current_user()
    with conn() as c: rows=c.execute('SELECT * FROM complaints').fetchall() if u['role']=='admin' else c.execute('SELECT * FROM complaints WHERE user_id=?',(u['id'],)).fetchall()
    out=[]
    for r in rows:
        usr=get_user(r['user_id']);out.append(dict(id=r['id'],user=user_dict(usr),subject=r['subject'],message=r['message'],status=r['status'],response=r['response'],created_at=r['created_at']))
    return jsonify(complaints=out)
@app.get('/api/admin/summary')
@require_role('admin')
def admin_summary():
    with conn() as c:return jsonify(customers=c.execute("SELECT count(*) FROM users WHERE role='customer'").fetchone()[0],providers=c.execute('SELECT count(*) FROM providers').fetchone()[0],pending_providers=c.execute("SELECT count(*) FROM providers WHERE status='Pending'").fetchone()[0],vehicles=c.execute('SELECT count(*) FROM vehicles').fetchone()[0],pending_vehicles=c.execute("SELECT count(*) FROM vehicles WHERE status='Pending'").fetchone()[0],bookings=c.execute('SELECT count(*) FROM bookings').fetchone()[0],payments=c.execute('SELECT count(*) FROM payments').fetchone()[0],complaints=c.execute("SELECT count(*) FROM complaints WHERE status='Open'").fetchone()[0])
@app.get('/api/admin/providers')
@require_role('admin')
def admin_providers():
    with conn() as c:rows=c.execute('SELECT * FROM providers').fetchall()
    return jsonify(providers=[dict(id=p['id'],user=user_dict(get_user(p['user_id'])),business_name=p['business_name'],phone=p['phone'],address=p['address'],status=p['status']) for p in rows])
@app.post('/api/admin/providers/<int:pid>/<action>')
@require_role('admin')
def provider_action(pid,action):
    if action not in ['approve','reject']:return jsonify(error='Invalid action.'),400
    with conn() as c:p=c.execute('SELECT * FROM providers WHERE id=?',(pid,)).fetchone()
    if not p:return jsonify(error='Provider not found.'),404
    with conn() as c:c.execute('UPDATE providers SET status=? WHERE id=?',('Approved' if action=='approve' else 'Rejected',pid))
    return jsonify(status='Approved' if action=='approve' else 'Rejected')
@app.get('/api/admin/vehicles')
@require_role('admin')
def admin_vehicles():
    with conn() as c:rows=c.execute('SELECT * FROM vehicles').fetchall()
    return jsonify(vehicles=[vehicle_dict(x) for x in rows])
@app.post('/api/admin/vehicles/<int:vid>/<action>')
@require_role('admin')
def vehicle_action(vid,action):
    if action not in ['approve','reject']:return jsonify(error='Invalid action.'),400
    with conn() as c:v=c.execute('SELECT * FROM vehicles WHERE id=?',(vid,)).fetchone()
    if not v:return jsonify(error='Vehicle not found.'),404
    with conn() as c:c.execute('UPDATE vehicles SET status=? WHERE id=?',('Approved' if action=='approve' else 'Rejected',vid))
    return jsonify(status='Approved' if action=='approve' else 'Rejected')
@app.get('/api/admin/customers')
@require_role('admin')
def admin_customers():
    with conn() as c:rows=c.execute("SELECT * FROM users WHERE role='customer'").fetchall()
    return jsonify(customers=[user_dict(u) for u in rows])
@app.get('/api/admin/payments')
@require_role('admin')
def admin_payments():
    with conn() as c:rows=c.execute('SELECT * FROM payments').fetchall()
    return jsonify(payments=[dict(id=p['id'],booking_id=p['booking_id'],amount=p['amount'],status=p['status'],method=p['method'],transaction_ref=p['transaction_ref'],created_at=p['created_at']) for p in rows])
@app.post('/api/admin/complaints/<int:cid>/resolve')
@require_role('admin')
def resolve_complaint(cid):
    d=request.get_json(silent=True) or {}
    with conn() as c:c.execute('UPDATE complaints SET status=?,response=? WHERE id=?',('Resolved',d.get('response','Resolved by admin'),cid))
    return jsonify(status='Resolved')
@app.post('/api/admin/users/<int:uid>/block')
@require_role('admin')
def block_user(uid):
    with conn() as c:u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if not u:return jsonify(error='User not found.'),404
    st='Active' if u['status']=='Blocked' else 'Blocked'
    with conn() as c:c.execute('UPDATE users SET status=? WHERE id=?',(st,uid))
    return jsonify(status=st)
@app.get('/api/admin/bookings')
@require_role('admin')
def admin_bookings():return list_bookings()
if __name__=='__main__':app.run(host='127.0.0.1',port=5000,debug=False)
