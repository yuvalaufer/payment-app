# app.py
from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import os
import locale
from datetime import datetime, timedelta
from flask_httpauth import HTTPBasicAuth 
import git 
from dotenv import load_dotenv 

# --- טעינת משתני סביבה (לגישה ל-GIT) ---
load_dotenv()
GIT_TOKEN = os.environ.get("GIT_TOKEN")
GIT_REPO_URL = os.environ.get('RENDER_GIT_REPO_URL') or os.environ.get('GIT_REPO_URL')
# --- סוף טעינת משתני סביבה ---

# --- הגדרות נתיבים ---
DATA_DIR = '.' 
DATABASE = os.path.join(DATA_DIR, 'payments.db')
STUDENT_LIST_FILE = os.path.join(DATA_DIR, 'student_list.txt')
# --- סוף הגדרות נתיבים ---

DEFAULT_MONTHLY_FEE = 330 
STATUS_OPTIONS = ['לא שולם', 'שולם', 'שולם חלקי']

# 🚨 שינוי קריטי: REPO מוגדר כעת כ-None גלובלי
REPO = None 
# 🚨 הוספת פונקציה לבדיקה וטעינה עצלה של REPO
def get_repo():
    """מאתחל או מחזיר את אובייקט ה-Git Repo המאומת."""
    global REPO
    if REPO is None:
        REPO = setup_git_repo()
    return REPO

# --- פונקציות GIT - לכידת שגיאות משופרת ---
def setup_git_repo():
    """מאתחל את רפוזיטורי ה-Git המקומי ומושך נתונים עדכניים."""
    try:
        repo_path = os.getcwd()
        repo = None
        
        # 1. אתחול/טעינת הרפוזיטורי
        if not os.path.exists(os.path.join(repo_path, '.git')):
            print("INFO: Initializing new repository.")
            repo = git.Repo.init(repo_path)
            
            git_url = GIT_REPO_URL
            
            if git_url and GIT_TOKEN:
                
                # 🛠️ פורמט URL: https://oauth2:TOKEN@github.com/...
                if git_url.startswith("https://"):
                    auth_url = f"https://oauth2:{GIT_TOKEN}@{git_url[8:]}" 
                else:
                    auth_url = git_url
                
                # יצירת Remote
                try:
                    if not repo.remotes:
                         print("INFO: Creating remote 'origin'.")
                         repo.create_remote('origin', auth_url)
                except git.exc.GitCommandError as git_err:
                     print(f"FATAL ERROR: Failed to create Git remote with auth URL: {git_err}")
                     return None

            # --- 2. משיכת נתונים (ניסיון Fetch) ---
            try:
                if repo and repo.remotes:
                    print("INFO: Attempting Git FETCH to verify authentication.")
                    # שימוש ב-fetch() במקום pull() כדי לקבל אינדיקציה ברורה יותר לשגיאת אימות
                    repo.remotes.origin.fetch()
                    
                    # אם ה-fetch הצליח, נבצע checkout
                    if repo.heads:
                        remote_main_branch = [ref for ref in repo.remotes.origin.refs if ref.name.endswith('/main') or ref.name.endswith('/master')]
                        
                        if remote_main_branch:
                            branch_name = remote_main_branch[0].remote_head
                            repo.git.checkout(branch_name) 
                            print(f"INFO: Successfully checked out branch: {branch_name}")
                        else:
                            print("ERROR: Could not determine primary branch name (main/master).")
                            repo.remotes.origin.pull() # fallback to pull
                    
                    
            except Exception as e:
                # 🚨 זו השורה הקריטית שתספר לנו אם ה-TOKEN או ה-URL שגויים
                print(f"CRITICAL AUTH ERROR: Git Fetch/Checkout failed: {e}")
                
        else:
            repo = git.Repo(repo_path)
            # --- 2. משיכת נתונים קיימים ---
            try:
                if repo.remotes:
                    print("INFO: Pulling latest data from GitHub (existing repo).")
                    repo.remotes.origin.pull()
            except Exception as e:
                print(f"ERROR: Git pull failed (CHECK GIT_TOKEN AND URL!): {e}")
            
        # 3. הגדרת פרטי המשתמש ל-Commit
        if repo:
             repo.config_writer().set_value('user', 'email', 'render-bot@example.com').release()
             repo.config_writer().set_value('user', 'name', 'Render Data Bot').release()
        return repo
    except Exception as e:
        print(f"FATAL ERROR: Git setup failed entirely (General Error): {e}")
        return None

def commit_data(repo_instance, message="Data update from web app"):
    """שומר את קבצי הנתונים ב-GitHub."""
    if not repo_instance: 
        return False
        
    try:
        if os.path.exists(DATABASE):
            repo_instance.index.add([DATABASE])
        if os.path.exists(STUDENT_LIST_FILE):
            repo_instance.index.add([STUDENT_LIST_FILE])

        if not repo_instance.index.diff(None):
            return True 

        repo_instance.index.commit(message)
        
        if GIT_TOKEN:
            repo_instance.remote('origin').push()
            print("INFO: Data pushed to GitHub successfully.")
            return True
        else:
            print("ERROR: GIT_TOKEN not set for push.")
            return False

    except Exception as e:
        print(f"ERROR: Git commit/push failed: {e}")
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

# DEBUG CHECK:
print(f"DEBUG CHECK: GIT_TOKEN is set: {bool(GIT_TOKEN)}")
print(f"DEBUG CHECK: GIT_REPO_URL is set: {bool(GIT_REPO_URL)}") 

# 🚨 קריאה כפויה ל-Git Setup מיד לאחר בדיקת המשתנים
get_repo() 

app = Flask(__name__)
app.config['SECRET_KEY'] = '1A2B3C4D5E6F7G8H9I0J_SUPER_SECRET' 

# ----------------------------------------------------
#                הגדרת אימות (Basic Auth)
# ----------------------------------------------------

auth = HTTPBasicAuth()
USERS = {
    os.environ.get("ADMIN_USER", "admin_default"): os.environ.get("ADMIN_PASS", "default_pass") 
}

@auth.verify_password
def verify_password(username, password):
    # חוסם התחברות עם סיסמת הדיפולט מחשש אבטחה
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
                  (DEFAULT_MONTHLY_FEE, 'your_email_disabled@example.com')) 

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
    
    commit_data(get_repo(), message="Updated student list")


if not os.path.exists(STUDENT_LIST_FILE):
    save_student_list(["דוגמא אברהם", "לוי משה", "כהן שרה"])
    
    
# --- ניתובים (Routes) ---

@app.route('/', methods=['GET', 'POST'])
@auth.login_required
def index():
    conn = get_db_connection()
    settings = conn.execute("SELECT monthly_fee, report_email FROM settings WHERE id = 1").fetchone()
    current_master_list = load_student_list() 
    
    # --- לוגיקה לחישוב רשימת חודשים (סדר עולה) ---
    months = set()
    
    today = datetime.now()
    for i in range(12): 
        month_obj = today.replace(day=1) + timedelta(days=32 * i)
        month_obj = month_obj.replace(day=1) 
        months.add(month_obj.strftime("%B %Y"))
        
    db_months = conn.execute("SELECT DISTINCT month FROM payments").fetchall()
    for row in db_months:
        months.add(row['month'])
        
    sorted_months = sorted(list(months), key=lambda x: datetime.strptime(x, "%B %Y"), reverse=False) 
    
    if not sorted_months:
        sorted_months = [today.strftime("%B %Y")]

    current_month = request.args.get('month') or request.form.get('selected_month') or sorted_months[-1]
    # --- סוף לוגיקת חודשים ---
    
    payments_data = {}
    db_payments = conn.execute("SELECT * FROM payments WHERE month = ?", (current_month,)).fetchall()
    
    students_with_past_data = set()
    for row in db_payments:
        payments_data[row['student_name']] = dict(row)
        students_with_past_data.add(row['student_name'])

    # רשימה סופית: תלמידי מאסטר נוכחיים + תלמידים עם היסטוריית תשלום לחודש זה (להקפאת הרכב התלמידים)
    final_students = sorted(list(students_with_past_data.union(set(current_master_list))))

    report_data = []
    total_paid = 0 
    
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

        total_paid += paid_amount 

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
                           months=sorted_months,
                           current_month=current_month,
                           settings=settings,
                           report_data=report_data,
                           status_options=STATUS_OPTIONS,
                           students_text=students_text,
                           total_paid=total_paid)

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
        
        commit_data(get_repo(), message="Updated global settings")

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

        for student in
