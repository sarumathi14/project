import sqlite3
from flask import g
from datetime import datetime
import hashlib

DATABASE = 'health.db'

def get_db():
    from flask import current_app
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'patient',
            phone TEXT,
            age INTEGER,
            gender TEXT,
            specialization TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            date TEXT,
            reason TEXT,
            token_number INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            FOREIGN KEY (patient_id) REFERENCES users(id),
            FOREIGN KEY (doctor_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS health_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            diagnosis TEXT,
            prescription TEXT,
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY (patient_id) REFERENCES users(id),
            FOREIGN KEY (doctor_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT DEFAULT 'emergency',
            message TEXT,
            lat TEXT,
            lng TEXT,
            status TEXT DEFAULT 'sent',
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS vitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            heart_rate INTEGER,
            bp_sys INTEGER,
            bp_dia INTEGER,
            spo2 REAL,
            temperature REAL,
            glucose INTEGER,
            recorded_at TEXT,
            FOREIGN KEY (patient_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS health_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER UNIQUE NOT NULL,
            blood_group TEXT,
            allergies TEXT,
            chronic_diseases TEXT,
            past_surgeries TEXT,
            current_medications TEXT,
            last_updated TEXT,
            FOREIGN KEY (patient_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT,
            file_path TEXT,
            file_type TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id)
        );
    ''')

    # Seed admin
    existing = conn.execute("SELECT id FROM users WHERE email='admin@smarthealth.com'").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (name,email,password,role,created_at) VALUES (?,?,?,?,?)",
            ('Admin', 'admin@smarthealth.com', hash_pw('admin123'), 'admin', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )

    # Seed demo doctors
    doctors_data = [
        ('Dr. Sarah Johnson', 'sarah@smarthealth.com', 'doctor123', 'doctor', '+1-555-0101', 42, 'Female', 'Cardiology'),
        ('Dr. Michael Chen', 'michael@smarthealth.com', 'doctor123', 'doctor', '+1-555-0102', 38, 'Male', 'Neurology'),
        ('Dr. Priya Patel', 'priya@smarthealth.com', 'doctor123', 'doctor', '+1-555-0103', 35, 'Female', 'General Medicine'),
        ('Dr. James Wilson', 'james@smarthealth.com', 'doctor123', 'doctor', '+1-555-0104', 50, 'Male', 'Orthopedics'),
    ]
    for d in doctors_data:
        ex = conn.execute("SELECT id FROM users WHERE email=?", (d[1],)).fetchone()
        if not ex:
            conn.execute(
                "INSERT INTO users (name,email,password,role,phone,age,gender,specialization,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (d[0], d[1], hash_pw(d[2]), d[3], d[4], d[5], d[6], d[7], datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )

    # Seed demo patients
    patients_data = [
        ('Alice Brown', 'alice@gmail.com', 'patient123', 'patient', '+1-555-0201', 28, 'Female'),
        ('Bob Smith', 'bob@gmail.com', 'patient123', 'patient', '+1-555-0202', 45, 'Male'),
        ('Carol Davis', 'carol@gmail.com', 'patient123', 'patient', '+1-555-0203', 33, 'Female'),
        ('David Lee', 'david@gmail.com', 'patient123', 'patient', '+1-555-0204', 60, 'Male'),
        ('Emma White', 'emma@gmail.com', 'patient123', 'patient', '+1-555-0205', 22, 'Female'),
    ]
    for p in patients_data:
        ex = conn.execute("SELECT id FROM users WHERE email=?", (p[1],)).fetchone()
        if not ex:
            conn.execute(
                "INSERT INTO users (name,email,password,role,phone,age,gender,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (p[0], p[1], hash_pw(p[2]), p[3], p[4], p[5], p[6], datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )

    conn.commit()

    # Seed appointments
    from datetime import date, timedelta
    doc_ids = [row['id'] for row in conn.execute("SELECT id FROM users WHERE role='doctor'").fetchall()]
    pat_ids = [row['id'] for row in conn.execute("SELECT id FROM users WHERE role='patient'").fetchall()]
    appt_count = conn.execute("SELECT COUNT(*) as c FROM appointments").fetchone()['c']
    if appt_count == 0 and doc_ids and pat_ids:
        import random
        statuses = ['pending', 'completed', 'cancelled', 'in_progress']
        for i in range(20):
            d_appt = (date.today() - timedelta(days=random.randint(0, 30))).strftime('%Y-%m-%d')
            conn.execute(
                "INSERT INTO appointments (patient_id,doctor_id,date,reason,token_number,status,created_at) VALUES (?,?,?,?,?,?,?)",
                (random.choice(pat_ids), random.choice(doc_ids), d_appt,
                 random.choice(['Follow-up', 'General checkup', 'Heart checkup', 'Fever', 'Blood pressure']),
                 random.randint(1, 15), random.choice(statuses),
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
        conn.commit()

    # Seed health records
    rec_count = conn.execute("SELECT COUNT(*) as c FROM health_records").fetchone()['c']
    if rec_count == 0 and doc_ids and pat_ids:
        import random
        diagnoses = ['Hypertension', 'Diabetes Type 2', 'Anxiety', 'Common Cold', 'Migraine']
        prescriptions = ['Amlodipine 5mg', 'Metformin 500mg', 'Alprazolam 0.5mg', 'Paracetamol 500mg', 'Sumatriptan 50mg']
        for i in range(10):
            conn.execute(
                "INSERT INTO health_records (patient_id,doctor_id,diagnosis,prescription,notes,created_at) VALUES (?,?,?,?,?,?)",
                (random.choice(pat_ids), random.choice(doc_ids),
                 random.choice(diagnoses), random.choice(prescriptions),
                 'Patient advised rest and follow-up in 2 weeks.',
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
        conn.commit()

    conn.close()
    print("[✓] Database initialized successfully.")
