# app.py
from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import os
import locale
from datetime import datetime

# --- הגדרות נתיבים לשימוש עם Persistent Disk ב-Render ---
DATA_DIR = '/var/data'
DATABASE = os.path.join(DATA_DIR, 'payments.db')
STUDENT_LIST_FILE = os.path.join(DATA_DIR, 'student_list.txt')
# --- סוף הגדרות נתיבים ---

DEFAULT_MONTHLY_FEE = 1000 
STATUS_OPTIONS = ['לא שולם', 'שולם', 'שולם חלקי']

# הגדרת שפה לעברית עבור תאריכים
try:
    locale.setlocale(locale.LC_ALL, 'he_IL.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'he_IL')
    except:
        pass 

# ודא שתיקיית הנתונים קיימת
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

app = Flask(__name__)
app.config['SECRET_KEY'] = '1A2B3C4D5E6F7G8H9I0J_SUPER_SECRET' 


# --- פונקציות עזר לבסיס הנתונים ---

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. טבלת הגדרות גלובליות
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            monthly_fee INTEGER,
            report_email TEXT
        )
    """)
    
    c.execute("SELECT COUNT(*) FROM settings")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO settings (id, monthly_fee, report_email) VALUES (1, ?, ?)", 
                  (DEFAULT_MONTHLY_FEE, 'your_email@example.com'))

    # 2. טבלת נתוני תשלומים פר חודש
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY,
            month TEXT NOT NULL,
            student_name TEXT NOT NULL,
            status TEXT DEFAULT 'לא שולם',
            paid_amount INTEGER DEFAULT 0,
            UNIQUE(month, student_name)
        )
    """)
    conn.commit()
    conn.close()

init_db()


# --- פונקציות עזר לקבצים ---

def load_student_list():
    if not os.path.exists(STUDENT_LIST_FILE):
        return []
    with open(STUDENT_LIST_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def save_student_list(students):
    with open(STUDENT_LIST_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(students))

if not os.path.exists(STUDENT_LIST_FILE):
    save_student_list(["דוגמא אברהם", "לוי משה", "כהן שרה"])
    
    
# --- ניתובים (Routes) ---

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db_connection()
    
    settings = conn.execute("SELECT monthly_fee, report_email FROM settings WHERE id = 1").fetchone()
    students = load_student_list()
    
    months = [datetime.now().strftime("%B %Y")]
    db_months = conn.execute("SELECT DISTINCT month FROM payments ORDER BY month DESC").fetchall()
    for row in db_months:
        if row['month'] not in months:
            months.append(row['month'])
            
    current_month = request.args.get('month') or request.form.get('selected_month') or months[0]
    
    payments_data = {}
    db_payments = conn.execute("SELECT * FROM payments WHERE month = ?", (current_month,)).fetchall()
    for row in db_payments:
        payments_data[row['student_name']] = dict(row)

    report_data = []
    for student in students:
        payment = payments_data.get(student, {})
        status = payment.get('status', 'לא שולם')
        paid_amount = payment.get('paid_amount', 0)
        
        if status == 'שולם':
            remaining = 0
            paid_amount = settings['monthly_fee']
        elif status == 'שולם חלקי':
            remaining = settings['monthly_fee'] - paid_amount
        else:
            remaining = settings['monthly_fee']
            paid_amount = 0

        report_data.append({
            'name': student,
            'status': status,
            'paid_amount': paid_amount,
            'remaining': remaining,
            'fee': settings['monthly_fee'] 
        })

    conn.close()
    
    return render_template('index.html', 
                           months=months,
                           current_month=current_month,
                           settings=settings,
                           report_data=report_data,
                           status_options=STATUS_OPTIONS)

@app.route('/update_settings', methods=['POST'])
def update_settings():
    try:
        new_fee = int(request.form['monthly_fee'])
        new_email = request.form['report_email']
        
        conn = get_db_connection()
        conn.execute("UPDATE settings SET monthly_fee = ?, report_email = ? WHERE id = 1",
                     (new_fee, new_email))
        conn.commit()
        conn.close()
        return redirect(url_for('index', message='ההגדרות נשמרו בהצלחה!'))
    except Exception as e:
        return f"אירעה שגיאה בעת שמירת ההגדרות: {e}", 500

@app.route('/update_payments', methods=['POST'])
def update_payments():
    current_month = request.form['month']
    students = load_student_list()
    conn = get_db_connection()
    
    try:
        settings = conn.execute("SELECT monthly_fee FROM settings WHERE id = 1").fetchone()
        monthly_fee = settings['monthly_fee']
        
        for student in students:
            status = request.form.get(f'status_{student}')
            paid_amount_str = request.form.get(f'paid_{student}')
            
            paid_amount = int(paid_amount_str) if paid_amount_str and paid_amount_str.isdigit() else 0

            if status == 'שולם':
                paid_amount = monthly_fee
            elif status == 'לא שולם':
                paid_amount = 0

            conn.execute("""
                INSERT OR REPLACE INTO payments (month, student_name, status, paid_amount)
                VALUES (?, ?, ?, ?)
            """, (current_month, student, status, paid_amount))
            
        conn.commit()
        conn.close()
        return redirect(url_for('index', month=current_month, message='התשלומים נשמרו בהצלחה!'))
    except Exception as e:
        return f"אירעה שגיאה בעת שמירת התשלומים: {e}", 500


@app.route('/delete_month', methods=['POST'])
def delete_month():
    month_to_delete = request.form.get('month_to_delete')
    
    if not month_to_delete:
        return "שם החודש אינו חוקי.", 400
        
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM payments WHERE month = ?", (month_to_delete,))
        conn.commit()
        conn.close()
        
        return redirect(url_for('index', message=f'הנתונים לחודש {month_to_delete} נמחקו בהצלחה!'))
    except Exception as e:
        return f"אירעה שגיאה במחיקת נתונים: {e}", 500


@app.route('/send_report', methods=['POST'])
def send_report():
    current_month = request.form.get('month')
    # זוהי פונקציית דמה. מימוש מלא דורש הגדרת Gmail API (OAuth 2.0)
    return redirect(url_for('index', month=current_month, message=f'דוח לחודש {current_month} נשלח למייל (פונקציית דמה).'))


if __name__ == '__main__':
    app.run(debug=True)
