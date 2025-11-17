# app.py

import sqlite3
import datetime
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)
app.secret_key = 'your_secret_key' # נדרש לשמירת סשנים/הודעות
DATABASE = 'payments.db'
STATUS_OPTIONS = ['שולם', 'שולם חלקי', 'לא שולם']

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    # פונקציה ליצירת טבלאות אם אינן קיימות
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            month TEXT NOT NULL,
            student_name TEXT NOT NULL,
            status TEXT NOT NULL,
            paid_amount INTEGER NOT NULL,
            PRIMARY KEY (month, student_name)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            monthly_fee INTEGER NOT NULL,
            report_email TEXT
        )
    ''')
    # הכנסת הגדרות ברירת מחדל אם הטבלה ריקה
    if conn.execute('SELECT COUNT(*) FROM settings').fetchone()[0] == 0:
        conn.execute('INSERT INTO settings (monthly_fee, report_email) VALUES (?, ?)', (350, 'placeholder@example.com'))
    
    conn.commit()
    conn.close()

init_db()

# פונקציות עזר 
def get_students(conn):
    students = conn.execute('SELECT name FROM students ORDER BY name').fetchall()
    return [s['name'] for s in students]

def get_settings(conn):
    return conn.execute('SELECT monthly_fee, report_email FROM settings WHERE id = 1').fetchone()

def get_current_month_str():
    return datetime.date.today().strftime("%Y-%m")

def get_available_months(conn):
    months = conn.execute('SELECT DISTINCT month FROM payments ORDER BY month DESC').fetchall()
    if not months:
        return [get_current_month_str()]
    return [m['month'] for m in months]

def get_report_data(conn, month):
    settings = get_settings(conn)
    monthly_fee = settings['monthly_fee']
    
    students = get_students(conn)
    report_data = []
    total_paid = 0

    for name in students:
        payment = conn.execute(
            'SELECT status, paid_amount FROM payments WHERE month = ? AND student_name = ?',
            (month, name)
        ).fetchone()

        if payment:
            status = payment['status']
            paid_amount = payment['paid_amount']
        else:
            status = 'לא שולם'
            paid_amount = 0

        # חישוב יתרה
        remaining = monthly_fee - paid_amount
        if remaining < 0: remaining = 0
        
        total_paid += paid_amount

        report_data.append({
            'name': name,
            'fee': monthly_fee,
            'status': status,
            'paid_amount': paid_amount,
            'remaining': remaining
        })
        
    return report_data, total_paid

# --- ניתובים (Routes) ---

@app.route('/')
def index():
    conn = get_db_connection()
    
    months = get_available_months(conn)
    current_month = request.args.get('month')
    
    if not current_month or current_month not in months:
        current_month = get_current_month_str()
        if current_month not in months:
            months.append(current_month)

    report_data, total_paid = get_report_data(conn, current_month)
    settings = get_settings(conn)
    students_text = "\n".join(get_students(conn))
    
    conn.close()

    return render_template(
        'index.html',
        current_month=current_month,
        months=sorted(months, reverse=True),
        report_data=report_data,
        total_paid=total_paid,
        settings=settings,
        students_text=students_text,
        status_options=STATUS_OPTIONS
    )

@app.route('/update_settings', methods=['POST'])
def update_settings():
    monthly_fee = request.form['monthly_fee']
    # שמירה של שדה המייל הישן (שנשלח כ-Hidden Input מה-HTML)
    report_email = request.form.get('report_email', 'placeholder@example.com') 
    
    conn = get_db_connection()
    conn.execute(
        'UPDATE settings SET monthly_fee = ?, report_email = ? WHERE id = 1',
        (monthly_fee, report_email)
    )
    conn.commit()
    conn.close()

    return redirect(url_for('index', message='ההגדרות עודכנו בהצלחה!'))

@app.route('/edit_students', methods=['POST'])
def edit_students():
    students_text = request.form['students_list
