# app.py
from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import os
import locale
from datetime import datetime, timedelta
# שימוש ב-timedelta עבור טווח חודשים פשוט (במקום dateutil)
from flask_httpauth import HTTPBasicAuth 
import git 
from dotenv import load_dotenv 

# --- טעינת משתני סביבה (לגישה ל-GIT) ---
load_dotenv()
GIT_TOKEN = os.environ.get("GIT_TOKEN")
# --- סוף טעינת משתני סביבה ---

# --- הגדרות נתיבים (שמירה בתיקייה מקומית זמנית, נשמרת ל-GitHub) ---
DATA_DIR = '.' 
DATABASE = os.path.join(DATA_DIR, 'payments.db')
STUDENT_LIST_FILE = os.path.join(DATA_DIR, 'student_list.txt')
# --- סוף הגדרות נתיבים ---

DEFAULT_MONTHLY_FEE = 1000 
STATUS_OPTIONS = ['לא שולם', 'שולם', 'שולם חלקי']

# --- פונקציות GIT (תיקון שמירת הנתונים) ---
def setup_git_repo():
    """מאתחל את רפוזיטורי ה-Git המקומי ומושך נתונים עדכניים."""
    try:
        repo_path = os.getcwd()
        repo = None
        
        # 1. אתחול/טעינת הרפוזיטורי
        if not os.path.exists(os.path.join(repo_path, '.git')):
            print("INFO: Initializing new repository.")
            repo = git.Repo.init(repo_path)
            
            git_url = os.environ.get('RENDER_GIT_REPO_URL') or os.environ.get('GIT_REPO_URL')
            
            if git_url and GIT_TOKEN:
                # הגדרת ה-remote URL עם ה-Token לצורך Pull/Push
                auth_url = git_url.replace("https://", f"https://oauth2:{GIT_TOKEN}@")
                repo.create_remote('origin', auth_url)
                
            # אם יש קבצים קיימים ב-GitHub, מושכים אותם כעת
            try:
                if repo.remotes:
                    print("INFO: Pulling latest data from GitHub.")
                    repo.remotes.origin.pull() # <-- משיכת הנתונים הקיימים
            except Exception as e:
                # ייתכן שאין קבצים ב-GitHub עדיין, זה בסדר
                print(f"WARNING: Initial Git pull failed (might be first run): {e}")

        else:
            repo = git.Repo(repo_path)
            # גם בהפעלה חוזרת, מוודאים שמושכים את הנתונים העדכניים
            try:
                print("INFO: Pulling latest data from GitHub.")
                repo.remotes.origin.pull() # <-- משיכת הנתונים הקיימים
            except Exception as e:
                print(f"WARNING: Git pull failed: {e}")
            
        # 2. הגדרת פרטי המשתמש ל-Commit
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
        if not repo.index.diff(None):
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
        # repo.remote('origin').config_writer.set('url', repo.remote('origin').url.split('@')[-1])
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
    
    # --- לוגיקה לחישוב רשימת חודשים (תיקון בעיה 1: סדר עולה) ---
    months = set()
    
    # הוסף את 12 החודשים הנוכחיים והבאים
    today = datetime.now()
    # משתמשים ב-timedelta כיוון שאין dateutil
    for i in range(12): 
        # יצירת אובייקט תאריך עבור תחילת החודש ה-i
        month_obj = today.replace(day=1) + timedelta(days=32 * i)
        month_obj = month_obj.replace(day=1) 
        months.add(month_obj.strftime("%
