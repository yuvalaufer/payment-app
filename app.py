# app.py

import sqlite3
import datetime
import smtplib, ssl
from email.message import EmailMessage 
from flask import Flask, render_template, request, redirect, url_for, session
from functools import wraps

app = Flask(__name__)

# --- הגדרות סודיות ואבטחה ---
# *** חובה לשנות את המפתחות הללו! ***
app.secret_key = 'YOUR_SECRET_KEY_FOR_SESSIONS' 
USERNAME = 'user'
PASSWORD = '123' 
# *** פרטי המייל לשליחה (חובה לעדכן) ***
SENDER_EMAIL = "your_email@example.com"
EMAIL_PASSWORD = "your_app_password" # זו צריכה להיות סיסמת אפליקציה אם משתמשים בג'ימייל
SMTP_SERVER = "smtp.gmail.com" 
SMTP_PORT = 465 
# ***********************************

DATABASE = 'payments.db'
STATUS_OPTIONS = ['שולם', 'שולם חלקי', 'לא שולם']

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # יצירת טבלת students
    conn.execute('''
        CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)
    ''')
    # יצירת טבלת payments
    conn.execute('''
        CREATE TABLE IF NOT EXISTS payments (month TEXT NOT NULL, student_name TEXT NOT NULL, status TEXT NOT NULL, paid_amount INTEGER NOT NULL, PRIMARY KEY (month, student_name))
    ''')
    # יצירת טבלת settings
    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, monthly_fee INTEGER NOT NULL, report_email TEXT)
    ''')
    # הכנסת הגדרות ברירת מחדל: 330
    if conn.execute('SELECT COUNT(*) FROM settings').fetchone()[0] == 0:
        conn.execute('INSERT INTO settings (monthly_fee, report_email) VALUES (?, ?)', (330, 'placeholder@example.com'))
    
    conn.commit()
    conn.close()

init_db()

# פונקציית דקורטור להגבלת גישה
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- פונקציות עזר ---

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['username'] != USERNAME or request.form['password'] != PASSWORD:
            error = 'שם משתמש או סיסמה שגויים.'
        else:
            session['logged_in'] = True
            return redirect(url_for('index'))
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/send_report', methods=['POST'])
@login_required 
def send_report():
    month = request.form['month_to_report']
    
    conn = get_db_connection()
    report_data, total_paid = get_report_data(conn, month)
    settings = get_settings(conn)
    conn.close()

    recipient = settings['report_email']
    if not recipient or recipient == 'placeholder@example.com':
        return redirect(url_for('index', month=month, message='שגיאה: הגדרת דוא"ל ריקה. עדכן בהגדרות.'))

    # בניית גוף המייל
    body = f"דוח תשלומים לחודש: {month}\n\n"
    body += f"סכום חודשי רצוי: {settings['monthly_fee']} ₪\n"
    body += f"סה\"כ תשלומים שהתקבלו: {total_paid} ₪\n\n"
    body += "פירוט תשלומים:\n"
    for item in report_data:
        body += f"- {item['name']}: סטטוס: {item['status']}, שולם: {item['paid_amount']} ₪, נותר: {item['remaining']} ₪\n"
    
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = f"דוח תשלומי אנסמבל חודש {month}"
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SENDER_EMAIL, EMAIL_PASSWORD)
            server.send_message(msg)
        message = f'דוח חודש {month} נשלח בהצלחה ל-{recipient}!'
    except Exception as e:
        message = f'שגיאה בשליחת המייל: ודא שפרטי המייל והסיסמה נכונים. שגיאה: {e}'
    
    return redirect(url_for('index', month=month, message=message))


@app.route('/')
@login_required
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
@login_required
def update_settings():
    monthly_fee = request.form['monthly_fee']
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
@login_required
def edit_students():
    students_text = request.form['students_list'].strip()
    new_students = [name.strip() for name in students_text.split('\n') if name.strip()]

    conn = get_db_connection()
    old_students = get_students(conn)
    
    students_to_remove = set(old_students) - set(new_students)
    
    for name in students_to_remove:
        conn.execute('DELETE FROM students WHERE name = ?', (name,))
        conn.execute('DELETE FROM payments WHERE student_name = ?', (name,))

    for name in new_students:
        conn.execute('INSERT OR IGNORE INTO students (name) VALUES (?)', (name,))
        
    conn.commit()
    conn.close()

    return redirect(url_for('index', message='רשימת התלמידים עודכנה בהצלחה!'))

@app.route('/update_payments', methods=['POST'])
@login_required
def update_payments():
    month = request.form['month']
    conn = get_db_connection()
    students = get_students(conn)
    
    for name in students:
        status = request.form.get(f'status_{name}')
        paid_amount_str = request.form.get(f'paid_{name}', '0')
        
        try:
            paid_amount = int(paid_amount_str)
        except ValueError:
            paid_amount = 0

        conn.execute(
            '''
            INSERT OR REPLACE INTO payments 
            (month, student_name, status, paid_amount) 
            VALUES (?, ?, ?, ?)
            ''',
            (month, name, status, paid_amount)
        )
        
    conn.commit()
    conn.close()

    return redirect(url_for('index', month=month, message=f'תשלומי חודש {month} עודכנו בהצלחה!'))

@app.route('/delete_month', methods=['POST'])
@login_required
def delete_month():
    month_to_delete = request.form['month_to_delete']
    conn = get_db_connection()
    conn.execute('DELETE FROM payments WHERE month = ?', (month_to_delete,))
    conn.commit()
    conn.close()

    return redirect(url_for('index', message=f'נתוני התשלום לחודש {month_to_delete} נמחקו בהצלחה.'))

if __name__ == '__main__':
    app.run(debug=True)

# end app.py
