from flask import Flask, render_template, request, session, redirect, url_for, flash
import wikipedia
from deep_translator import GoogleTranslator
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = 'crab_secret_key_123' # Change this in production

# Use absolute path for database file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Railway persistent storage support
if os.environ.get('RAILWAY_ENVIRONMENT'):
    # Files in /app/data will persist if you add a Volume in Railway
    DB_PATH = '/app/data/database.db'
    # Automatically create the data folder if it doesn't exist
    if not os.path.exists('/app/data'):
        os.makedirs('/app/data')
else:
    DB_PATH = os.path.join(BASE_DIR, 'database.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT UNIQUE NOT NULL, 
                  password_hash TEXT NOT NULL)''')
    # History table with user_id
    c.execute('''CREATE TABLE IF NOT EXISTS history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER,
                  query TEXT, 
                  result TEXT, 
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Login Required Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def landing():
    return render_template("home.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                         (username, generate_password_hash(password)))
            conn.commit()
            flash("Account created! Please log in.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists.", "error")
        finally:
            conn.close()
            
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('app_interface'))
        else:
            flash("Invalid username or password.", "error")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('landing'))

@app.route("/app")
@login_required
def app_interface():
    conn = get_db_connection()
    history = conn.execute('SELECT * FROM history WHERE user_id = ? ORDER BY timestamp DESC', 
                           (session['user_id'],)).fetchall()
    conn.close()
    return render_template("index.html", history=history)

@app.route("/run")
@login_required
def run():
    query = request.args.get("query")
    translate_req = request.args.get("translate") == "true"
    detailed_req = request.args.get("detailed") == "true"
    from_history = request.args.get("from_history") == "true"
    result = ""
    translation = ""

    try:
        # Toggle between concise (2) and detailed (5) sentences
        sentence_count = 5 if detailed_req else 2
        
        # Standard Wikipedia summary
        result = wikipedia.summary(query, sentences=sentence_count)
        
        # Performance optional Tamil translation separately
        # ONLY if detailed mode is NOT requested (show only in english for detail as per request)
        if translate_req and result and not detailed_req:
            translation = GoogleTranslator(source='auto', target='ta').translate(result)
            
    except wikipedia.exceptions.DisambiguationError:
        result = "There are multiple matches for this query. Please be more specific."
    except wikipedia.exceptions.PageError:
        result = "I could not find a page for that query."
    except Exception as e:
        result = f"An error occurred: {str(e)}"

    if query and result:
        conn = get_db_connection()
        
        # Only save to history if it's a NEW search (not from history and not an expansion)
        if not from_history and not detailed_req:
            conn.execute('INSERT INTO history (user_id, query, result) VALUES (?, ?, ?)', 
                         (session['user_id'], query, result))
            conn.commit()
            
        history = conn.execute('SELECT * FROM history WHERE user_id = ? ORDER BY timestamp DESC', 
                               (session['user_id'],)).fetchall()
        conn.close()
    else:
        conn = get_db_connection()
        history = conn.execute('SELECT * FROM history WHERE user_id = ? ORDER BY timestamp DESC', 
                               (session['user_id'],)).fetchall()
        conn.close()

    return render_template("index.html", 
                         query=query,
                         result=result, 
                         translation=translation, 
                         history=history, 
                         translate_checked=translate_req,
                         detailed_checked=detailed_req)

@app.route("/delete_history/<int:id>", methods=["POST"])
@login_required
def delete_history(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM history WHERE id = ? AND user_id = ?', (id, session['user_id']))
    conn.commit()
    conn.close()
    return "OK"

@app.route("/delete_all_history", methods=["POST"])
@login_required
def delete_all_history():
    conn = get_db_connection()
    conn.execute('DELETE FROM history WHERE user_id = ?', (session['user_id'],))
    conn.commit()
    conn.close()
    return "OK"

init_db()

if __name__ == "__main__":
    app.run(debug=True)
