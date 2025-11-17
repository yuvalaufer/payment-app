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
    conn = get_db_connection()
    # יצירת טבלת students
    conn.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    # יצירת טבלת payments
    conn.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            month TEXT NOT NULL,
            student_name TEXT NOT NULL,
            status TEXT NOT NULL,
            paid_amount INTEGER NOT NULL,
            PRIMARY KEY (month, student_name)
        )
    ''')
    # יצירת טבלת settings
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

# ניתוב ראשי
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

# ניתוב לעדכון הגדרות
@app.route('/update_settings', methods=['POST'])
def update_settings():
    monthly_fee = request.form['monthly_fee']
    # שדה המייל לא נדרש יותר
    report_email = request.form.get('report_email', 'placeholder@example.com') 
    
    conn = get_db_connection()
    conn.execute(
        'UPDATE settings SET monthly_fee = ?, report_email = ? WHERE id = 1',
        (monthly_fee, report_email)
    )
    conn.commit()
    conn.close()

    return redirect(url_for('index', message='ההגדרות עודכנו בהצלחה!'))

# ניתוב לעדכון רשימת תלמידים
@app.route('/edit_students', methods=['POST'])
def edit_students():
    students_text = request.form['students_list'].strip()
    new_students = [name.strip() for name in students_text.split('\n') if name.strip()]

    conn = get_db_connection()
    old_students = get_students(conn)
    
    # זיהוי תלמידים להסרה
    students_to_remove = set(old_students) - set(new_students)
    
    # הסרת תלמידים ישנים ותשלומיהם
    for name in students_to_remove:
        conn.execute('DELETE FROM students WHERE name = ?', (name,))
        conn.execute('DELETE FROM payments WHERE student_name = ?', (name,))

    # הוספת תלמידים חדשים (התעלם מקיימים)
    for name in new_students:
        conn.execute('INSERT OR IGNORE INTO students (name) VALUES (?)', (name,))
        
    conn.commit()
    conn.close()

    return redirect(url_for('index', message='רשימת התלמידים עודכנה בהצלחה!'))

# ניתוב לעדכון תשלומים
@app.route('/update_payments', methods=['POST'])
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

        # הכנסה או עדכון של נתוני תשלום
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

# ניתוב למחיקת חודש
@app.route('/delete_month', methods=['POST'])
def delete_month():
    month_to_delete = request.form['month_to_delete']
    conn = get_db_connection()
    conn.execute('DELETE FROM payments WHERE month = ?', (month_to_delete,))
    conn.commit()
    conn.close()

    return redirect(url_for('index', message=f'נתוני התשלום לחודש {month_to_delete} נמחקו בהצלחה.'))

if __name__ == '__main__':
    app.run(debug=True)
