from flask import Flask, render_template, request, redirect, session, Response
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from math import radians, cos, sin, sqrt, atan2
from io import StringIO
import csv
import os

app = Flask(__name__)

# ================= SECRET =================
app.secret_key = "secret123#1415ESEC"

# ================= ADMIN =================
ALLOWED_ADMIN_EMAIL = "dl.1415.info@schools.sa.edu.au"
ADMIN_PIN = "admin123#1415ESEC"

# ================= DATABASE =================
database_url = os.environ.get("DATABASE_URL")

if not database_url:
    database_url = "sqlite:///database.db"

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ================= TIME =================
def now_sa():
    return datetime.utcnow() + timedelta(hours=9, minutes=30)

# ================= SITE LOCATION =================
SITES = [
    {
        "name": "Plympton",
        "lat": -34.9622,
        "lon": 138.5485
    },
    {
        "name": "Parafield Gardens",
        "lat": -34.7926,
        "lon": 138.6127
    }
]

# Allowed distance in metres
MAX_DISTANCE = 150

# ================= DISTANCE CHECK =================
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # metres

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c

# ================= MODELS =================
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    mobile = db.Column(db.String(20), unique=True)
    role = db.Column(db.String(50))
    signature = db.Column(db.Text)
    accepted_terms = db.Column(db.Boolean, default=False)


class Log(db.Model):
    __tablename__ = "logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    sign_in = db.Column(db.DateTime)
    sign_out = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.Text)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

# ================= CREATE DB =================
with app.app_context():
    db.create_all()

    admin = User.query.filter_by(email=ALLOWED_ADMIN_EMAIL).first()
    if not admin:
        db.session.add(User(
            name="Admin",
            email=ALLOWED_ADMIN_EMAIL,
            mobile="0000000000",
            role="admin",
            signature="Admin",
            accepted_terms=True
        ))
        db.session.commit()

# ================= ROUTES =================

@app.route('/')
def home():
    return render_template("index.html")


@app.route('/get-started')
def get_started():
    return render_template("get_started.html")


@app.route('/returning')
def returning():
    return render_template("login.html")

# ================= LOGIN (WITH SITE CHECK) =================
@app.route('/login', methods=['POST'])
def login():

    login_id = request.form.get('login_id', '').lower().strip()
    pin = request.form.get('pin')
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')

    # ================= GPS VALIDATION =================
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except:
        return render_template("login.html", error="Location access required")

    # ================= CHECK SITE PROXIMITY =================
    allowed = False
    used_site = None

    for site in SITES:
        distance = calculate_distance(
            latitude,
            longitude,
            site["lat"],
            site["lon"]
        )

        if distance <= MAX_DISTANCE:
            allowed = True
            used_site = site["name"]
            break

    if not allowed:
        return f"""
        <h2>Access Denied</h2>
        <p>You are not at an approved site.</p>
        <p>Your distance is too far from all locations.</p>
        """

    # ================= ADMIN LOGIN =================
    if login_id == ALLOWED_ADMIN_EMAIL:

        if pin != ADMIN_PIN:
            return render_template("login.html", error="Invalid admin PIN")

        user = User.query.filter_by(email=ALLOWED_ADMIN_EMAIL).first()

    else:
        user = User.query.filter(
            (User.email == login_id) |
            (User.mobile == login_id)
        ).first()

    if not user:
        return render_template("login.html", error="User not found")

    # ================= ACTIVE LOGIN CHECK =================
    active_log = Log.query.filter_by(user_id=user.id, sign_out=None).first()

    if active_log:
        return render_template("login.html", error="You are already signed in.")

    # ================= SAVE LOGIN =================
    new_log = Log(
        user_id=user.id,
        sign_in=now_sa(),
        latitude=latitude,
        longitude=longitude
    )

    db.session.add(new_log)
    db.session.commit()

    session['user_id'] = user.id
    session['role'] = user.role
    session['site'] = used_site  # ✅ kept feature

    return redirect('/dashboard')

# ================= REGISTER =================
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        name = request.form['name']
        email = request.form['email'].lower().strip()
        mobile = request.form['mobile']
        role = request.form['role'].lower().strip()
        signature = request.form['signature']
        accepted_terms = request.form.get('terms')

        if not accepted_terms:
            return "You must accept terms"

        if role == "admin" and email != ALLOWED_ADMIN_EMAIL:
            return "Not allowed to register as admin"

        existing_user = User.query.filter(
            (User.email == email) | (User.mobile == mobile)
        ).first()

        if existing_user:
            return "User already exists"

        db.session.add(User(
            name=name,
            email=email,
            mobile=mobile,
            role=role,
            signature=signature,
            accepted_terms=True
        ))
        db.session.commit()

        return redirect('/returning')

    return render_template("register.html")

# ================= DASHBOARD =================
@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect('/returning')

    user = User.query.get(session['user_id'])

    if not user:
        session.clear()
        return redirect('/returning')

    latest_log = Log.query.filter_by(user_id=user.id).order_by(Log.id.desc()).first()

    signin_time = "N/A"
    if latest_log and latest_log.sign_in:
        signin_time = latest_log.sign_in.strftime("%d/%m/%Y %H:%M")

    return render_template(
        "dashboard.html",
        name=user.name,
        role=user.role,
        signin_time=signin_time,
        site=session.get('site')  # optional display
    )
# ==================================================
# AUTO SIGN OUT AT 7PM
# ==================================================
def auto_signout_expired_users():

    now = now_sa()

    today_7pm = now.replace(
        hour=19,
        minute=0,
        second=0,
        microsecond=0
    )

    if now >= today_7pm:

        active_logs = Log.query.filter_by(
            sign_out=None
        ).all()

        for log in active_logs:
            log.sign_out = now_sa()

        db.session.commit()
# ==================================================
# SIGN OUT PAGE
# ==================================================
@app.route('/signout')
def signout_page():
    return render_template("signout.html")

# ==================================================
# LOGOUT
# ==================================================
@app.route('/logout', methods=['POST'])
def logout():

    login_id = request.form.get('login_id')

    user = User.query.filter(
        (User.email == login_id) |
        (User.mobile == login_id)
    ).first()

    if not user:
        return "User not found"

    log = Log.query.filter_by(
        user_id=user.id,
        sign_out=None
    ).first()

    if log:
        log.sign_out = now_sa()
        db.session.commit()

    session.clear()

    return redirect('/next')

# ==================================================
# TERMS
# ==================================================
@app.route('/terms')
def terms():
    return render_template("terms.html")


# ================= NEXT =================
@app.route('/next')
def next_visitor():
    return render_template("next.html")

# ================= REPORT =================
@app.route('/report')
def report():

    if session.get('role') != 'admin':
        return "Access denied"

    data = db.session.query(
        User.name,
        User.mobile,
        User.role,
        Log.sign_in,
        Log.sign_out,
        Log.note
    ).join(Log, User.id == Log.user_id).all()

    return render_template("report.html", data=data)

# ================= CSV EXPORT =================
@app.route('/export/csv')
def export_csv():

    if session.get('role') != 'admin':
        return "Access denied"

    rows = db.session.query(
        User.name,
        User.mobile,
        User.role,
        Log.sign_in,
        Log.sign_out,
        Log.note
    ).join(Log, User.id == Log.user_id).all()

    si = StringIO()
    writer = csv.writer(si)

    writer.writerow(["Name", "Mobile", "Role", "Sign In", "Sign Out", "Note"])
    writer.writerows(rows)

    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=report.csv"}
    )

# ================= RUN =================
if __name__ == '__main__':
    app.run(debug=True)
