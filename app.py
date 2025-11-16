# app.py
from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import os
import locale
from datetime import datetime
from flask_httpauth import HTTPBasicAuth 
import git 
from dotenv import load_dotenv 

# --- טעינת משתני סביבה (לגישה ל-GIT) ---
load_dotenv()
# משתמש ב-os.environ.get לכל המשתנים
GIT_TOKEN = os.environ.get("GIT_TOKEN")
# --- סוף טעינת משתני סביבה ---

# --- הגדרות נתיבים (שמירה בתיקייה מקומית זמנית, נשמרת ל-GitHub) ---
DATA_DIR = '.' 
DATABASE = os.path.join(DATA_DIR, 'payments.db')
STUDENT_LIST_FILE = os.path.join(DATA_DIR, 'student_list.txt')
# --- סוף הגדרות נתיבים ---

DEFAULT_MONTHLY_FEE = 1000 
STATUS_OPTIONS = ['לא שולם', 'שולם', 'שולם חלקי']

# --- פונקציות GIT ---
def setup_git_repo():
    """מאתחל את רפוזיטורי ה-Git המקומי. פועל אוטומטית בפריסה הראשונה."""
    try:
        repo_path = os.getcwd()
        if not os.path.exists(os.path.join(repo_path, '.git')):
            print("INFO: Initializing repository.")
            
            # Render מעתיק את הקבצים מה-GitHub, לכן אנחנו רק צריכים לאתחל את ה-Repo המקומי
            repo = git.Repo.init(repo_path)
            
            # הוספת ה-remote של GitHub כדי שנוכל לבצע Push
            git_url = os.environ.get('RENDER_GIT_REPO_URL') or os.environ.get('GIT_REPO_URL')
            
            if git_url and GIT_TOKEN:
                # הוספת Token ל-URL לצורך אימות ב-Push
                auth_url = git_url.replace("https://", f"https://oauth2:{GIT_TOKEN}@")
                repo.create_remote('origin', auth_url)
            
        else:
            repo = git.Repo(repo_path)

        # הגדרת פרטי המשתמש ל-Commit
        repo.config_writer().set_value('user', 'email', 'render-bot@example.com').release()
        repo.config_writer().set_value('user', 'name', 'Render Data Bot').release()
        return repo
    except Exception as e:
        print(f"ERROR: Git setup failed: {e}")
        return None

def commit_data(repo, message="Data update from web app"):
    """שומר את קבצי הנתונים ב-GitHub."""
    if not repo:
        return False
        
    try:
        # 1. מוודא שה-DB וקובץ התלמידים נמצאים תחת מעקב
        if os.path.exists(DATABASE):
            repo.index.add([DATABASE])
        if os.path.exists(STUDENT_LIST_FILE):
            repo.index.add([STUDENT_LIST_FILE])

        # אם אין שינויים, לא ממשיך
        if not repo.index.diff(None): # בדיקה מול ה-index
            return True 

        # 2. מבצע Commit
        repo.index.commit(message)
        
        # 3. מבצע Push
        if GIT_TOKEN:
            repo.remote('origin').push()
            print("INFO: Data pushed to GitHub successfully.")
            return True
        else:
            print("ERROR: GIT_TOKEN not set for push.")
            return False

    except Exception as e:
        print(f"ERROR: Git commit/push failed: {e}")
        # ניקוי מידע רגיש מה-remote URL במקרה של כשל
        repo.remote('origin').config_writer.set('url', repo.remote('origin').url.split('@')[-1])
        return False
# --- סוף פונקציות GIT ---


# הגדרת שפה לעברית עבור תאריכים
try:
    locale.setlocale(locale.LC_ALL, 'he_IL.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'he_IL')
    except:
        pass 

# אתחול ה-repo לפני הפעלת האפליקציה
# זה ירוץ פעם אחת בהפעלה הראשונה של השרת
REPO = setup_git_repo()

app = Flask(__name__)
app.config['SECRET_KEY'] = '1A2B3C4D5E6F7G8H9I0J_SUPER_SECRET' 

# ----------------------------------------------------
#               הגדרת אימות (Basic Auth)
# ----------------------------------------------------

auth = HTTPBasicAuth()
USERS = {
    os.environ.get("ADMIN_USER", "admin_default"): os.environ.get("ADMIN_PASS", "default_pass") 
}

@auth.verify_password
def verify_password(username, password):
    if username in USERS and USERS.get(username) == password and password != "default_pass":
        return username
    return None

# ----------------------------------------------------

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
    cleaned_students = [s.strip() for s in students if s.strip()] 
    with open(STUDENT_LIST_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(cleaned_students))
    
    # *** שמירת השינוי ב-GitHub ***
    commit_data(REPO, message="Updated student list")


if not os.path.exists(STUDENT_LIST_FILE):
    save_student_list(["דוגמא אברהם", "לוי משה", "כהן שרה"])
    
    
# --- ניתובים (Routes) ---

@app.route('/', methods=['GET', 'POST'])
@auth.login_required
def index():
    conn = get_db_connection()
    
    settings = conn.execute("SELECT monthly_fee, report_email FROM settings WHERE id = 1").fetchone()
    current_master_list = load_student_list() 
    
    months = [datetime.now().strftime("%B %Y")]
    db_months = conn.execute("SELECT DISTINCT month FROM payments ORDER BY month DESC").fetchall()
    for row in db_months:
        if row['month'] not in months:
            months.append(row['month'])
            
    current_month = request.args.get('month') or request.form.get('selected_month') or months[0]
    
    payments_data = {}
    db_payments = conn.execute("SELECT * FROM payments WHERE month = ?", (current_month,)).fetchall()
    
    students_with_past_data = set()
    for row in db_payments:
        payments_data[row['student_name']] = dict(row)
        students_with_past_data.add(row['student_name'])

    final_students = sorted(list(students_with_past_data.union(set(current_master_list))))

    report_data = []
    for student in final_students: 
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
    
    students_text = "\n".join(load_student_list()) 
    
    return render_template('index.html', 
                           months=months,
                           current_month=current_month,
                           settings=settings,
                           report_data=report_data,
                           status_options=STATUS_OPTIONS,
                           students_text=students_text)

@app.route('/update_settings', methods=['POST'])
@auth.login_required 
def update_settings():
    try:
        new_fee = int(request.form['monthly_fee'])
        new_email = request.form['report_email']
        
        conn = get_db_connection()
        conn.execute("UPDATE settings SET monthly_fee = ?, report_email = ? WHERE id = 1",
                     (new_fee, new_email))
        conn.commit()
        conn.close()
        
        # *** שמירת השינוי ב-GitHub ***
        commit_data(REPO, message="Updated global settings")

        return redirect(url_for('index', message='ההגדרות נשמרו בהצלחה!'))
    except Exception as e:
        return f"אירעה שגיאה בעת שמירת ההגדרות: {e}", 500

@app.route('/update_payments', methods=['POST'])
@auth.login_required 
def update_payments():
    current_month = request.form['month']
    students = load_student_list()
    conn = get_db_connection()
    
    try:
        settings = conn.execute("SELECT monthly_fee FROM settings WHERE id = 1").fetchone()
        monthly_fee = settings['monthly_fee']
        
        db_payments = conn.execute("SELECT * FROM payments WHERE month = ?", (current_month,)).fetchall()
        students_with_past_data = set(row['student_name'] for row in db_payments)
        final_students = students_with_past_data.union(set(students))

        for student in final_students:
            status = request.form.get(f'status_{student}')
            paid_amount_str = request.form.get(f'paid_{student}')
            
            if not status:
                continue

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
        
        # *** שמירת השינוי ב-GitHub ***
        commit_data(REPO, message=f"Updated payments for {current_month}")

        return redirect(url_for('index', month=current_month, message='התשלומים נשמרו בהצלחה!'))
    except Exception as e:
        return f"אירעה שגיאה בעת שמירת התשלומים: {e}", 500

@app.route('/edit_students', methods=['POST'])
@auth.login_required
def edit_students():
    students_text = request.form['students_list']
    new_students = students_text.split('\n')
    
    save_student_list(new_students) # הפונקציה כבר עושה Commit
    
    return redirect(url_for('index', message='רשימת התלמידים עודכנה בהצלחה!'))


@app.route('/delete_month', methods=['POST'])
@auth.login_required 
def delete_month():
    month_to_delete = request.form.get('month_to_delete')
    
    if not month_to_delete:
        return "שם החודש אינו חוקי.", 400
        
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM payments WHERE month = ?", (month_to_delete,))
        conn.commit()
        conn.close()
        
        # *** שמירת השינוי ב-GitHub ***
        commit_data(REPO, message=f"Deleted data for {month_to_delete}")
        
        return redirect(url_for('index', message=f'הנתונים לחודש {month_to_delete} נמחקו בהצלחה!'))
    except Exception as e:
        return f"אירעה שגיאה במחיקת נתונים: {e}", 500


@app.route('/send_report', methods=['POST'])
@auth.login_required 
def send_report():
    current_month = request.form.get('month')
    # זוהי פונקציית דמה.
    return redirect(url_for('index', month=current_month, message=f'דוח לחודש {current_month} נשלח למייל (פונקציית דמה).'))


if __name__ == '__main__':
    app.run(debug=True)

#end app.py
