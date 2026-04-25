from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_socketio import SocketIO, emit, join_room, leave_room
from database import init_db, get_db, close_db
import json
import random
import math
from datetime import datetime, timedelta
import hashlib

app = Flask(__name__)
app.secret_key = 'smarthealthsecret2024'
socketio = SocketIO(app, cors_allowed_origins="*")

# Online users tracking: {user_id: {sid: socket_id, name: name, role: role}}
online_users = {}

import os
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp3', 'mp4', 'webm', 'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app.teardown_appcontext(close_db)

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def generate_vitals():
    return {
        'heart_rate': random.randint(60, 100),
        'blood_pressure_sys': random.randint(110, 140),
        'blood_pressure_dia': random.randint(70, 90),
        'spo2': random.uniform(95, 100),
        'temperature': round(random.uniform(36.1, 37.5), 1),
        'glucose': random.randint(70, 140)
    }

# ─────────────────────────────────────────────
# Public Routes
# ─────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# ─────────────────────────────────────────────
# Auth Routes
# ─────────────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'patient')
        phone = request.form.get('phone', '')
        age = request.form.get('age', 0)
        gender = request.form.get('gender', '')
        specialization = request.form.get('specialization', '')

        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        db = get_db()
        existing = db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
        if existing:
            flash('Email already registered.', 'danger')
            return render_template('register.html')

        hashed = hash_password(password)
        db.execute(
            'INSERT INTO users (name, email, password, role, phone, age, gender, specialization, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (name, email, hashed, role, phone, age, gender, specialization, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        db.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        hashed = hash_password(password)
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email=? AND password=?', (email, hashed)).fetchone()
        if user:
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            session['email'] = user['email']
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'doctor':
                return redirect(url_for('doctor_dashboard'))
            else:
                return redirect(url_for('patient_dashboard'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))

# ─────────────────────────────────────────────
# Patient Routes
# ─────────────────────────────────────────────
@app.route('/patient/dashboard')
@login_required
def patient_dashboard():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    vitals = generate_vitals()
    appointments = db.execute(
        'SELECT a.*, u.name as doctor_name FROM appointments a JOIN users u ON a.doctor_id=u.id WHERE a.patient_id=? ORDER BY a.created_at DESC LIMIT 5',
        (session['user_id'],)
    ).fetchall()
    alerts = db.execute(
        'SELECT * FROM alerts WHERE user_id=? ORDER BY created_at DESC LIMIT 5',
        (session['user_id'],)
    ).fetchall()
    records = db.execute(
        'SELECT hr.*, u.name as doctor_name FROM health_records hr JOIN users u ON hr.doctor_id=u.id WHERE hr.patient_id=? ORDER BY hr.created_at DESC LIMIT 5',
        (session['user_id'],)
    ).fetchall()
    token = db.execute(
        'SELECT * FROM appointments WHERE patient_id=? AND status="pending" ORDER BY created_at DESC LIMIT 1',
        (session['user_id'],)
    ).fetchone()
    return render_template('patient/dashboard.html', user=user, vitals=vitals,
                           appointments=appointments, alerts=alerts, records=records, token=token)

@app.route('/patient/vitals')
@login_required
def patient_vitals():
    vitals = generate_vitals()
    history = []
    base = datetime.now()
    for i in range(24):
        t = base - timedelta(hours=23 - i)
        history.append({
            'time': t.strftime('%H:%M'),
            'hr': random.randint(60, 100),
            'bp_sys': random.randint(110, 145),
            'bp_dia': random.randint(68, 90),
            'spo2': round(random.uniform(94, 100), 1),
            'temp': round(random.uniform(36.0, 37.8), 1),
            'glucose': random.randint(70, 150)
        })
    return render_template('patient/vitals.html', vitals=vitals, history=json.dumps(history))

@app.route('/patient/appointments', methods=['GET', 'POST'])
@login_required
def patient_appointments():
    db = get_db()
    if request.method == 'POST':
        doctor_id = request.form.get('doctor_id')
        date = request.form.get('date')
        reason = request.form.get('reason')
        existing_count = db.execute(
            'SELECT COUNT(*) as cnt FROM appointments WHERE doctor_id=? AND date=? AND status!="cancelled"',
            (doctor_id, date)
        ).fetchone()['cnt']
        token_number = existing_count + 1
        db.execute(
            'INSERT INTO appointments (patient_id, doctor_id, date, reason, token_number, status, created_at) VALUES (?,?,?,?,?,?,?)',
            (session['user_id'], doctor_id, date, reason, token_number, 'pending', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        db.commit()
        flash(f'Appointment booked! Your token number is #{token_number}', 'success')
        return redirect(url_for('patient_appointments'))
    doctors = db.execute("SELECT * FROM users WHERE role='doctor'").fetchall()
    appointments = db.execute(
        'SELECT a.*, u.name as doctor_name FROM appointments a JOIN users u ON a.doctor_id=u.id WHERE a.patient_id=? ORDER BY a.created_at DESC',
        (session['user_id'],)
    ).fetchall()
    return render_template('patient/appointments.html', doctors=doctors, appointments=appointments)

@app.route('/patient/teleconsult')
@login_required
def patient_teleconsult():
    db = get_db()
    doctors = db.execute("SELECT * FROM users WHERE role='doctor'").fetchall()
    return render_template('patient/teleconsult.html', doctors=doctors)

@app.route('/patient/records')
@login_required
def patient_records():
    db = get_db()
    records = db.execute(
        'SELECT hr.*, u.name as doctor_name FROM health_records hr JOIN users u ON hr.doctor_id=u.id WHERE hr.patient_id=? ORDER BY hr.created_at DESC',
        (session['user_id'],)
    ).fetchall()
    return render_template('patient/records.html', records=records)

@app.route('/patient/emergency', methods=['GET', 'POST'])
@login_required
def patient_emergency():
    db = get_db()
    if request.method == 'POST':
        lat = request.form.get('lat', '0')
        lng = request.form.get('lng', '0')
        message = request.form.get('message', 'Emergency Alert')
        db.execute(
            'INSERT INTO alerts (user_id, type, message, lat, lng, status, created_at) VALUES (?,?,?,?,?,?,?)',
            (session['user_id'], 'emergency', message, lat, lng, 'sent', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        db.commit()
        flash('Emergency alert sent! Help is on the way.', 'danger')
        return redirect(url_for('patient_emergency'))
    alerts = db.execute(
        'SELECT * FROM alerts WHERE user_id=? ORDER BY created_at DESC',
        (session['user_id'],)
    ).fetchall()
    return render_template('patient/emergency.html', alerts=alerts)

@app.route('/patient/health_profile', methods=['GET', 'POST'])
@login_required
def patient_health_profile():
    db = get_db()
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        age = request.form.get('age')
        gender = request.form.get('gender')
        
        blood_group = request.form.get('blood_group')
        allergies = request.form.get('allergies')
        chronic_diseases = request.form.get('chronic_diseases')
        past_surgeries = request.form.get('past_surgeries')
        current_medications = request.form.get('current_medications')
        
        db.execute('UPDATE users SET name=?, phone=?, age=?, gender=? WHERE id=?',
                   (name, phone, age, gender, session['user_id']))
        
        existing = db.execute('SELECT id FROM health_details WHERE patient_id=?', (session['user_id'],)).fetchone()
        if existing:
            db.execute('''UPDATE health_details 
                          SET blood_group=?, allergies=?, chronic_diseases=?, past_surgeries=?, current_medications=?, last_updated=?
                          WHERE patient_id=?''',
                       (blood_group, allergies, chronic_diseases, past_surgeries, current_medications, 
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session['user_id']))
        else:
            db.execute('''INSERT INTO health_details 
                          (patient_id, blood_group, allergies, chronic_diseases, past_surgeries, current_medications, last_updated)
                          VALUES (?,?,?,?,?,?,?)''',
                       (session['user_id'], blood_group, allergies, chronic_diseases, past_surgeries, current_medications,
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        db.commit()
        flash('Health profile updated successfully!', 'success')
        return redirect(url_for('patient_health_profile'))
        
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    health = db.execute('SELECT * FROM health_details WHERE patient_id=?', (session['user_id'],)).fetchone()
    return render_template('patient/health_profile.html', user=user, health=health)

# ─────────────────────────────────────────────
# Doctor Routes
# ─────────────────────────────────────────────
@app.route('/doctor/dashboard')
@login_required
def doctor_dashboard():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    appointments = db.execute(
        'SELECT a.*, u.name as patient_name FROM appointments a JOIN users u ON a.patient_id=u.id WHERE a.doctor_id=? ORDER BY a.created_at DESC LIMIT 10',
        (session['user_id'],)
    ).fetchall()
    total_patients = db.execute(
        'SELECT COUNT(DISTINCT patient_id) as cnt FROM appointments WHERE doctor_id=?',
        (session['user_id'],)
    ).fetchone()['cnt']
    pending = db.execute(
        "SELECT COUNT(*) as cnt FROM appointments WHERE doctor_id=? AND status='pending'",
        (session['user_id'],)
    ).fetchone()['cnt']
    return render_template('doctor/dashboard.html', user=user, appointments=appointments,
                           total_patients=total_patients, pending=pending)

@app.route('/doctor/patients')
@login_required
def doctor_patients():
    db = get_db()
    patients = db.execute(
        '''SELECT DISTINCT u.* FROM users u 
           JOIN appointments a ON u.id=a.patient_id 
           WHERE a.doctor_id=? AND u.role="patient"''',
        (session['user_id'],)
    ).fetchall()
    return render_template('doctor/patients.html', patients=patients)

@app.route('/doctor/appointments')
@login_required
def doctor_appointments():
    db = get_db()
    appointments = db.execute(
        'SELECT a.*, u.name as patient_name FROM appointments a JOIN users u ON a.patient_id=u.id WHERE a.doctor_id=? ORDER BY a.date DESC',
        (session['user_id'],)
    ).fetchall()
    return render_template('doctor/appointments.html', appointments=appointments)

@app.route('/doctor/appointment/<int:appt_id>/update', methods=['POST'])
@login_required
def update_appointment(appt_id):
    db = get_db()
    status = request.form.get('status')
    db.execute('UPDATE appointments SET status=? WHERE id=? AND doctor_id=?',
               (status, appt_id, session['user_id']))
    db.commit()
    flash('Appointment updated.', 'success')
    return redirect(url_for('doctor_appointments'))

@app.route('/doctor/prescribe', methods=['GET', 'POST'])
@login_required
def doctor_prescribe():
    db = get_db()
    if request.method == 'POST':
        patient_id = request.form.get('patient_id')
        diagnosis = request.form.get('diagnosis')
        prescription = request.form.get('prescription')
        notes = request.form.get('notes')
        db.execute(
            'INSERT INTO health_records (patient_id, doctor_id, diagnosis, prescription, notes, created_at) VALUES (?,?,?,?,?,?)',
            (patient_id, session['user_id'], diagnosis, prescription, notes, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        db.commit()
        flash('Prescription saved.', 'success')
        return redirect(url_for('doctor_prescribe'))
    patients = db.execute(
        '''SELECT DISTINCT u.* FROM users u JOIN appointments a ON u.id=a.patient_id WHERE a.doctor_id=?''',
        (session['user_id'],)
    ).fetchall()
    return render_template('doctor/prescribe.html', patients=patients)

# ─────────────────────────────────────────────
# Admin Routes
# ─────────────────────────────────────────────
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) as cnt FROM users WHERE role!='admin'").fetchone()['cnt']
    total_patients = db.execute("SELECT COUNT(*) as cnt FROM users WHERE role='patient'").fetchone()['cnt']
    total_doctors = db.execute("SELECT COUNT(*) as cnt FROM users WHERE role='doctor'").fetchone()['cnt']
    total_appointments = db.execute("SELECT COUNT(*) as cnt FROM appointments").fetchone()['cnt']
    total_alerts = db.execute("SELECT COUNT(*) as cnt FROM alerts WHERE type='emergency'").fetchone()['cnt']
    total_records = db.execute("SELECT COUNT(*) as cnt FROM health_records").fetchone()['cnt']
    recent_users = db.execute("SELECT * FROM users WHERE role!='admin' ORDER BY created_at DESC LIMIT 8").fetchall()
    recent_appointments = db.execute(
        'SELECT a.*, u.name as patient_name, d.name as doctor_name FROM appointments a JOIN users u ON a.patient_id=u.id JOIN users d ON a.doctor_id=d.id ORDER BY a.created_at DESC LIMIT 5'
    ).fetchall()
    return render_template('admin/dashboard.html',
                           total_users=total_users, total_patients=total_patients,
                           total_doctors=total_doctors, total_appointments=total_appointments,
                           total_alerts=total_alerts, total_records=total_records,
                           recent_users=recent_users, recent_appointments=recent_appointments)

@app.route('/admin/users')
@admin_required
def admin_users():
    db = get_db()
    role = request.args.get('role', '')
    if role:
        users = db.execute("SELECT * FROM users WHERE role=? ORDER BY created_at DESC", (role,)).fetchall()
    else:
        users = db.execute("SELECT * FROM users WHERE role!='admin' ORDER BY created_at DESC").fetchall()
    return render_template('admin/users.html', users=users, role_filter=role)

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    db = get_db()
    db.execute('DELETE FROM users WHERE id=?', (user_id,))
    db.commit()
    flash('User deleted.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/appointments')
@admin_required
def admin_appointments():
    db = get_db()
    appointments = db.execute(
        'SELECT a.*, u.name as patient_name, d.name as doctor_name FROM appointments a JOIN users u ON a.patient_id=u.id JOIN users d ON a.doctor_id=d.id ORDER BY a.created_at DESC'
    ).fetchall()
    return render_template('admin/appointments.html', appointments=appointments)

@app.route('/admin/alerts')
@admin_required
def admin_alerts():
    db = get_db()
    alerts = db.execute(
        'SELECT al.*, u.name as user_name FROM alerts al JOIN users u ON al.user_id=u.id ORDER BY al.created_at DESC'
    ).fetchall()
    return render_template('admin/alerts.html', alerts=alerts)

@app.route('/admin/records')
@admin_required
def admin_records():
    db = get_db()
    records = db.execute(
        'SELECT hr.*, u.name as patient_name, d.name as doctor_name FROM health_records hr JOIN users u ON hr.patient_id=u.id JOIN users d ON hr.doctor_id=d.id ORDER BY hr.created_at DESC'
    ).fetchall()
    return render_template('admin/records.html', records=records)

@app.route('/admin/reports')
@admin_required
def admin_reports():
    db = get_db()
    # Appointment trend last 7 days
    appt_trend = []
    for i in range(6, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        cnt = db.execute("SELECT COUNT(*) as c FROM appointments WHERE date=?", (d,)).fetchone()['c']
        appt_trend.append({'date': d, 'count': cnt})
    # Generate graph data
    labels_24 = [(datetime.now() - timedelta(hours=23-i)).strftime('%H:%M') for i in range(24)]
    heart_rate_data = [random.randint(60, 100) for _ in range(24)]
    bp_sys_data = [random.randint(110, 145) for _ in range(24)]
    bp_dia_data = [random.randint(68, 90) for _ in range(24)]
    spo2_data = [round(random.uniform(94, 100), 1) for _ in range(24)]
    temp_data = [round(random.uniform(36.0, 37.8), 1) for _ in range(24)]
    glucose_data = [random.randint(70, 150) for _ in range(24)]

    # AI prediction
    risk_labels = ['Low Risk', 'Moderate Risk', 'High Risk', 'Critical']
    risk_data = [45, 30, 18, 7]

    # AI accuracy
    ai_acc_labels = ['Week 1', 'Week 2', 'Week 3', 'Week 4', 'Week 5']
    ai_acc_data = [88.2, 90.5, 91.0, 93.4, 95.1]

    # Token wait time
    token_labels = ['9AM', '10AM', '11AM', '12PM', '1PM', '2PM', '3PM', '4PM']
    token_wait = [5, 12, 18, 22, 15, 10, 8, 4]

    # Teleconsultation
    tele_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    tele_video = [15, 20, 18, 25, 22, 10, 8]
    tele_audio = [8, 12, 10, 14, 11, 6, 5]
    tele_chat = [20, 25, 22, 30, 28, 15, 12]

    # Emergency alerts
    alert_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
    alert_data = [5, 8, 6, 12, 9, 11]

    return render_template('admin/reports.html',
        labels_24=json.dumps(labels_24),
        heart_rate_data=json.dumps(heart_rate_data),
        bp_sys_data=json.dumps(bp_sys_data),
        bp_dia_data=json.dumps(bp_dia_data),
        spo2_data=json.dumps(spo2_data),
        temp_data=json.dumps(temp_data),
        glucose_data=json.dumps(glucose_data),
        risk_labels=json.dumps(risk_labels),
        risk_data=json.dumps(risk_data),
        ai_acc_labels=json.dumps(ai_acc_labels),
        ai_acc_data=json.dumps(ai_acc_data),
        token_labels=json.dumps(token_labels),
        token_wait=json.dumps(token_wait),
        tele_labels=json.dumps(tele_labels),
        tele_video=json.dumps(tele_video),
        tele_audio=json.dumps(tele_audio),
        tele_chat=json.dumps(tele_chat),
        alert_labels=json.dumps(alert_labels),
        alert_data=json.dumps(alert_data),
        appt_trend=json.dumps(appt_trend)
    )

@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) as cnt FROM users WHERE role!='admin'").fetchone()['cnt']
    total_patients = db.execute("SELECT COUNT(*) as cnt FROM users WHERE role='patient'").fetchone()['cnt']
    total_doctors = db.execute("SELECT COUNT(*) as cnt FROM users WHERE role='doctor'").fetchone()['cnt']
    total_appointments = db.execute("SELECT COUNT(*) as cnt FROM appointments").fetchone()['cnt']
    total_emergency = db.execute("SELECT COUNT(*) as cnt FROM alerts WHERE type='emergency'").fetchone()['cnt']
    # Monthly registrations (simulated)
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    patient_reg = [random.randint(5, 30) for _ in range(12)]
    doctor_reg = [random.randint(1, 10) for _ in range(12)]
    return render_template('admin/analytics.html',
                           total_users=total_users, total_patients=total_patients,
                           total_doctors=total_doctors, total_appointments=total_appointments,
                           total_emergency=total_emergency,
                           months=json.dumps(months),
                           patient_reg=json.dumps(patient_reg),
                           doctor_reg=json.dumps(doctor_reg))

# ─────────────────────────────────────────────
# API Routes (for AJAX)
# ─────────────────────────────────────────────
@app.route('/api/vitals/live')
@login_required
def api_vitals_live():
    return jsonify(generate_vitals())

@app.route('/api/token/status/<int:doctor_id>')
@login_required
def api_token_status(doctor_id):
    db = get_db()
    current = db.execute(
        "SELECT MIN(token_number) as current FROM appointments WHERE doctor_id=? AND status='in_progress'",
        (doctor_id,)
    ).fetchone()['current'] or 1
    waiting = db.execute(
        "SELECT COUNT(*) as cnt FROM appointments WHERE doctor_id=? AND status='pending'",
        (doctor_id,)
    ).fetchone()['cnt']
    return jsonify({'current_token': current, 'waiting': waiting, 'estimated_wait': waiting * 15})

@app.route('/chat/list')
@login_required
def chat_list():
    db = get_db()
    user_id = session['user_id']
    role = session['role']
    
    if role == 'patient':
        contacts = db.execute('''
            SELECT DISTINCT u.id, u.name, u.role, u.specialization 
            FROM users u
            JOIN appointments a ON (u.id = a.doctor_id OR u.id = a.patient_id)
            WHERE (a.patient_id = ? OR a.doctor_id = ?) AND u.id != ? AND u.role = 'doctor'
            UNION
            SELECT DISTINCT u.id, u.name, u.role, u.specialization
            FROM users u
            JOIN messages m ON (u.id = m.sender_id OR u.id = m.receiver_id)
            WHERE (m.sender_id = ? OR m.receiver_id = ?) AND u.id != ? AND u.role = 'doctor'
        ''', (user_id, user_id, user_id, user_id, user_id, user_id)).fetchall()
    else:
        contacts = db.execute('''
            SELECT DISTINCT u.id, u.name, u.role, u.phone, u.age, u.gender
            FROM users u
            JOIN appointments a ON (u.id = a.patient_id OR u.id = a.doctor_id)
            WHERE (a.doctor_id = ? OR a.patient_id = ?) AND u.id != ? AND u.role = 'patient'
            UNION
            SELECT DISTINCT u.id, u.name, u.role, u.phone, u.age, u.gender
            FROM users u
            JOIN messages m ON (u.id = m.sender_id OR u.id = m.receiver_id)
            WHERE (m.sender_id = ? OR m.receiver_id = ?) AND u.id != ? AND u.role = 'patient'
        ''', (user_id, user_id, user_id, user_id, user_id, user_id)).fetchall()
        
    return render_template('chat/list.html', contacts=contacts)

@app.route('/chat/<int:target_id>')
@login_required
def chat_session(target_id):
    db = get_db()
    user_id = session['user_id']
    target_user = db.execute('SELECT * FROM users WHERE id=?', (target_id,)).fetchone()
    if not target_user:
        flash('User not found.', 'danger')
        return redirect(url_for('chat_list'))
        
    db.execute('UPDATE messages SET is_read=1 WHERE sender_id=? AND receiver_id=?', (target_id, user_id))
    db.commit()
    
    messages = db.execute('''
        SELECT * FROM messages 
        WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
        ORDER BY created_at ASC
    ''', (user_id, target_id, target_id, user_id)).fetchall()
    
    return render_template('chat/chat.html', target_user=target_user, messages=messages)

@app.route('/chat/upload', methods=['POST'])
@login_required
def chat_upload():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        file = request.files['file']
        target_id = request.form.get('target_id')
        if not target_id:
            return jsonify({'error': 'No target_id provided'}), 400
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        
        if file and allowed_file(file.filename):
            from werkzeug.utils import secure_filename
            import uuid
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            file_url = url_for('static', filename='uploads/' + filename)
            file_type = 'image' if ext in {'png', 'jpg', 'jpeg', 'gif'} \
                        else ('video' if ext in {'mp4', 'webm'} \
                        else ('audio' if ext == 'mp3' else 'file'))
            
            # Save to DB
            sender_id = session['user_id']
            db = get_db()
            db.execute(
                'INSERT INTO messages (sender_id, receiver_id, message, file_path, file_type, created_at) VALUES (?,?,?,?,?,?)',
                (sender_id, int(target_id), file.filename, file_url, file_type, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            db.commit()
            
            # Emit via socket
            tid = int(target_id)
            if tid in online_users:
                target_sid = online_users[tid]['sid']
                print(f"[Socket] Sending media to {tid} ({target_sid})")
                socketio.emit('receive_message', {
                    'from_id': sender_id,
                    'from_name': session['name'],
                    'message': file.filename,
                    'file_path': file_url,
                    'file_type': file_type,
                    'time': datetime.now().strftime('%H:%M')
                }, room=target_sid)
                
            return jsonify({
                'success': True,
                'file_url': file_url,
                'file_type': file_type,
                'filename': file.filename,
                'time': datetime.now().strftime('%H:%M')
            })
        return jsonify({'error': 'Invalid file type'}), 400
    except Exception as e:
        print(f"[Error] Chat upload: {e}")
        return jsonify({'error': str(e)}), 500

# ─────────────────────────────────────────────
# SocketIO Events
# ─────────────────────────────────────────────
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        user_id = session['user_id']
        online_users[user_id] = {
            'sid': request.sid,
            'name': session['name'],
            'role': session['role']
        }
        # Notify others that someone came online
        emit('user_status_change', {'user_id': user_id, 'status': 'online'}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    try:
        user_id = None
        for uid, info in list(online_users.items()):
            if info['sid'] == request.sid:
                user_id = uid
                break
        
        if user_id:
            del online_users[user_id]
            print(f"[Socket] User {user_id} disconnected.")
            socketio.emit('user_status_change', {'user_id': user_id, 'status': 'offline'}, broadcast=True)
    except Exception as e:
        print(f"[Error] Disconnect: {e}")

@app.route('/debug/online')
def debug_online():
    return jsonify(online_users)

@socketio.on('call_request')
def handle_call_request(data):
    # data: { target_id: id, type: 'video'|'audio'|'chat' }
    target_id = int(data.get('target_id'))
    if target_id in online_users:
        target_sid = online_users[target_id]['sid']
        emit('incoming_call', {
            'from_id': session['user_id'],
            'from_name': session['name'],
            'type': data.get('type')
        }, room=target_sid)
    else:
        emit('call_error', {'message': 'User is currently offline.'})

@socketio.on('call_response')
def handle_call_response(data):
    # data: { target_id: id, accepted: true|false, type: type }
    target_id = int(data.get('target_id'))
    if target_id in online_users:
        target_sid = online_users[target_id]['sid']
        emit('call_status', {
            'accepted': data.get('accepted'),
            'from_id': session['user_id'],
            'from_name': session['name'],
            'type': data.get('type')
        }, room=target_sid)
        # Also notification for standard alerts which might expect 'doctor_name'
        emit('call_status', {
            'accepted': data.get('accepted'),
            'doctor_id': session['user_id'],
            'doctor_name': session['name'],
            'type': data.get('type')
        }, room=target_sid)

@socketio.on('webrtc_signal')
def handle_webrtc_signal(data):
    target_id = int(data.get('target_id'))
    if target_id in online_users:
        target_sid = online_users[target_id]['sid']
        emit('webrtc_signal', {
            'from_id': session['user_id'],
            'signal': data.get('signal')
        }, room=target_sid)

@socketio.on('send_message')
def handle_send_message(data):
    try:
        target_id = data.get('target_id')
        if not target_id: return
        target_id = int(target_id)
        sender_id = session.get('user_id')
        message_text = data.get('message', '').strip()
        file_path = data.get('file_path', None)
        file_type = data.get('file_type', 'text')
        
        if not sender_id or (not message_text and not file_path):
            return

        print(f"[Socket] Message from {sender_id} to {target_id}: {message_text[:20]}...")

        # Save to database
        import sqlite3
        conn = sqlite3.connect('health.db')
        conn.execute(
            'INSERT INTO messages (sender_id, receiver_id, message, file_path, file_type, created_at) VALUES (?,?,?,?,?,?)',
            (sender_id, target_id, message_text, file_path, file_type, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        conn.close()

        if target_id in online_users:
            target_sid = online_users[target_id]['sid']
            print(f"[Socket] Routing message to SID: {target_sid}")
            socketio.emit('receive_message', {
                'from_id': sender_id,
                'from_name': session.get('name', 'User'),
                'message': message_text,
                'file_path': file_path,
                'file_type': file_type,
                'time': datetime.now().strftime('%H:%M')
            }, room=target_sid)
        else:
            print(f"[Socket] User {target_id} is offline. Message saved to DB only.")
    except Exception as e:
        print(f"[Error] send_message: {e}")

@socketio.on('ping')
def handle_ping():
    emit('pong', {'time': datetime.now().strftime('%H:%M:%S')})

@socketio.on('typing')
def handle_typing(data):
    try:
        target_id = int(data.get('target_id'))
        if target_id in online_users:
            target_sid = online_users[target_id]['sid']
            socketio.emit('is_typing', {
                'from_id': session.get('user_id'),
                'is_typing': data.get('is_typing')
            }, room=target_sid)
    except:
        pass

@app.route('/api/online_doctors')
def api_online_doctors():
    doctors = [uid for uid, info in online_users.items() if info['role'] == 'doctor']
    return jsonify(doctors)

@app.route('/api/user_status/<int:uid>')
@login_required
def api_user_status(uid):
    # Returns online status for any user
    status = 'online' if uid in online_users else 'offline'
    return jsonify({'uid': uid, 'status': status})

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='127.0.0.1', port=5555, debug=True, use_reloader=False)
