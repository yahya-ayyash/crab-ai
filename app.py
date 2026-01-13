from flask import Flask, render_template, request, session, redirect, url_for, flash
# Importing the tool to translate text (Google Translate)
from deep_translator import GoogleTranslator
import sqlite3
import threading
import webbrowser
import time
# Tools for password security (hashing)
from werkzeug.security import generate_password_hash, check_password_hash
# Tools for making "decorators" (special functions that wrap other functions)
from functools import wraps
import os
# Importing AI providers
import g4f
from pytgpt.phind import PHIND
import sys

# PyInstaller fix for --noconsole: redirect stdout/stderr to a dummy writer if they are None
class DummyWriter:
    def write(self, *args, **kwargs):
        pass
    def flush(self):
        pass

if sys.stdout is None:
    sys.stdout = DummyWriter()
if sys.stderr is None:
    sys.stderr = DummyWriter()

# Initialize the Flask application
# Determine if running as a script or frozen exe
if getattr(sys, 'frozen', False):
    # If frozen, use AppData/Local/CRAB_AI for the database to keep the exe folder clean
    # This prevents the "database.db" file from appearing next to the exe
    app_data = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    BASE_DIR = os.path.join(app_data, 'CRAB_AI')
    
    # Create the directory if it doesn't exist
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
        
    # And use the temp directory (_MEIPASS) for static/templates
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    static_folder = os.path.join(sys._MEIPASS, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    # If running as script, use the current file's directory
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__)

app.secret_key = 'crab_secret_key_123' # Change this in production

# -------------------------
# DATABASE SETTINGS
# -------------------------
DB_PATH = os.path.join(BASE_DIR, 'database.db')

def init_db():
    """
    Initializes the database by creating necessary tables if they don't exist.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Users table: Stores username and secure password hash
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT UNIQUE NOT NULL, 
                  password_hash TEXT NOT NULL)''')
                  
    # 2. Chats table: Stores the list of conversations (threads)
    cursor.execute('''CREATE TABLE IF NOT EXISTS chats 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER,
                  title TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
                  
    # 3. History table: Stores individual messages within a chat
    cursor.execute('''CREATE TABLE IF NOT EXISTS history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER,
                  chat_id INTEGER,
                  query TEXT, 
                  result TEXT, 
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id),
                  FOREIGN KEY (chat_id) REFERENCES chats (id))''')
                  
    conn.commit() # Save changes
    conn.close()  # Close connection

def get_db_connection():
    """
    Helper function to get a connection to the database.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)  # Add timeout to prevent locks
    conn.row_factory = sqlite3.Row # Allows accessing columns by name (e.g., row['username'])
    return conn

# -------------------------
# SECURITY & AUTHENTICATION
# -------------------------

# Login Required Decorator
def login_required(view_function):
    """
    This is a 'decorator' that checks if a user is logged in before allowing access to a page.
    """
    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # Check if it's an background (AJAX) request
            if request.args.get('ajax') == 'true' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {"error": "Session expired. Please log in again.", "auth_error": True}, 401
            # If not logged in, redirect to login page
            return redirect(url_for('login'))
        return view_function(*args, **kwargs)
    return decorated_function

# Global Error Handler for AJAX
@app.errorhandler(Exception)
def handle_exception(e):
    """
    Handles errors globally. If it's a background request, return JSON error instead of crashing.
    """
    if request.args.get('ajax') == 'true' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        print(f"CRITICAL ERROR (AJAX): {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": f"Server error: {str(e)}"}, 500
    return str(e), 500

# -------------------------
# WEBSITE ROUTES (PAGES)
# -------------------------

@app.route("/")
def landing():
    # Shows the landing page (Home)
    return render_template("home.html")

@app.route("/about")
def about():
    # Shows the about page
    return render_template("about.html")

@app.route("/portfolio")
def portfolio():
    # Shows the portfolio page
    return render_template("portfolio.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    """
    Handles user registration.
    GET: Show the signup form.
    POST: Process the form data.
    """
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        conn = get_db_connection()
        try:
            # Store the user with a HASHED password (never store plain passwords!)
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
    """
    Handles user login.
    """
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        # Check if user exists AND if the password matches the hash
        if user and check_password_hash(user['password_hash'], password):
            # Save user info in the "session" (browser cookie)
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('app_interface'))
        else:
            flash("Invalid username or password.", "error")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    # Clear the session (log out)
    session.clear()
    return redirect(url_for('landing'))

# -------------------------
# APP INTERFACE & AI LOGIC
# -------------------------

@app.route("/app")
@app.route("/app/<int:chat_id>")
@login_required
def app_interface(chat_id=None):
    """
    The main chat interface.
    """
    conn = get_db_connection()
    # Fetch list of previous chats for the sidebar
    chats = conn.execute('SELECT * FROM chats WHERE user_id = ? ORDER BY timestamp DESC', 
                         (session['user_id'],)).fetchall()
    
    active_chat_id = chat_id
    history = []
    
    # If a specific chat is selected, load its message history
    if active_chat_id:
        history = conn.execute('SELECT * FROM history WHERE chat_id = ? ORDER BY timestamp ASC', 
                               (active_chat_id,)).fetchall()
    
    conn.close()
    return render_template("index.html", history=history, chats=chats, active_chat_id=active_chat_id)

@app.route("/new_chat")
@login_required
def new_chat():
    # Start a fresh conversation by removing the chat_id
    return redirect(url_for('app_interface'))

@app.route("/translate", methods=['POST'])
@login_required
def translate():
    """
    Translates text to Tamil using Google Translate.
    """
    data = request.get_json()
    text = data.get("text", "")
    if not text:
        return {"error": "No text provided"}, 400
    
    try:
        translation = GoogleTranslator(source='auto', target='ta').translate(text)
        return {"translation": translation}
    except Exception as e:
        print(f"Translation Error: {e}")
        return {"error": str(e)}, 500

@app.route("/run")
@login_required
def run():
    """
    THE MAIN AI FUNCTION.
    Takes the user's query, sends it to the AI, and returns the result.
    """
    query = request.args.get("query")
    # removed duplicate query line
    detailed_req = request.args.get("detailed") == "true"
    from_history = request.args.get("from_history") == "true"
    is_ajax = request.args.get("ajax") == "true"
    
    result = ""
    ai_success = False

    try:
        # 1. Fetch conversation history for context (last 5 interactions)
        conn = get_db_connection()
        past_interactions = conn.execute(
            'SELECT query, result FROM history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5',
            (session['user_id'],)
        ).fetchall()
        conn.close()

        # 2. Build the message list for the AI
        messages = [
            {"role": "system", "content": "You are CRAB (Advanced Voice Intelligence System) developed by Yahya. You are helpful, professional, and slightly futuristic. Keep responses concise but informative."}
        ]
        
        # Add past context in chronological order so the AI remembers what we said
        for interaction in reversed(past_interactions):
            messages.append({"role": "user", "content": interaction['query']})
            messages.append({"role": "assistant", "content": interaction['result']})
            
        # Add the current query
        if detailed_req:
            prompt = f"Provide a detailed explanation about: {query}"
        else:
            prompt = query
            
        messages.append({"role": "user", "content": prompt})
        
        # 3. Try obtaining a response from the AI
        
        # Primary: pytgpt (PHIND) - Generally more stable
        try:
            print("DEBUG: Attempting AI with pytgpt (PHIND)...")
            phind = PHIND()
            response = phind.chat(query=prompt)
            if response and len(response.strip()) > 0:
                result = response
                ai_success = True
                print("DEBUG: pytgpt (PHIND) succeeded!")
        except Exception as pytgpt_error:
            print(f"DEBUG: pytgpt failed: {pytgpt_error}")

        # Fallback: g4f (If PHIND fails, try these other providers)
        if not ai_success:
            print("DEBUG: Falling back to g4f providers...")
            providers = [
                (g4f.Provider.DeepInfra, g4f.models.default),
                (g4f.Provider.BlackboxPro, "gpt-4o"),
                (g4f.Provider.ApiAirforce, "gpt-4o-mini"),
            ]

            for provider, model in providers:
                try:
                    p_name = getattr(provider, '__name__', str(provider))
                    response = g4f.ChatCompletion.create(
                        model=model,
                        messages=messages,
                        provider=provider
                    )
                    if response and len(response.strip()) > 0:
                        result = response
                        ai_success = True
                        print(f"DEBUG: g4f {p_name} succeeded!")
                        break
                except Exception as prov_error:
                    print(f"DEBUG: g4f {p_name} failed: {prov_error}")
                    continue
        
        if result:
            # Filter out promotional lines from the AI response
            lines = result.split('\n')
            filtered_lines = [line for line in lines if "llmplayground.net" not in line]
            result = '\n'.join(filtered_lines).strip()

        if not ai_success:
            result = "I'm having trouble connecting to the AI service right now. Please try again in a moment."

    except Exception as e:
        print(f"Error in run: {e}")
        result = "An unexpected error occurred."
        ai_success = False

    # 4. Save the interaction to the database (History)
    history_id = None
    chat_id = request.args.get("chat_id")
    # Handle case where JS sends "null" string
    if chat_id == "null" or not chat_id: chat_id = None

    if ai_success and not from_history:
        conn = get_db_connection()
        
        # Create a new chat conversation if one doesn't exist
        if not chat_id:
            # Title is first 30 chars of query
            title = query[:30] + "..." if len(query) > 30 else query
            cursor = conn.execute('INSERT INTO chats (user_id, title) VALUES (?, ?)', (session['user_id'], title))
            chat_id = cursor.lastrowid
            conn.commit()

        cursor = conn.execute('INSERT INTO history (user_id, chat_id, query, result) VALUES (?, ?, ?, ?)', 
                             (session['user_id'], chat_id, query, result))
        history_id = cursor.lastrowid
        conn.commit()
        conn.close()

    # If this was a background request (AJAX), return JSON
    if is_ajax:
        return {
            "query": query,
            "result": result,
            "ai_success": ai_success,
            "history_id": history_id,
            "chat_id": chat_id
        }

    # Otherwise refresh the page
    return redirect(url_for('app_interface', chat_id=chat_id))

# -------------------------
# HISTORY ADJUSTMENT
# -------------------------

@app.route("/delete_history/<int:id>", methods=["POST"])
@login_required
def delete_history(id):
    # Deletes a single message
    conn = get_db_connection()
    conn.execute('DELETE FROM history WHERE id = ? AND user_id = ?', (id, session['user_id']))
    conn.commit()
    conn.close()
    return "OK"

@app.route("/delete_chat/<int:id>", methods=["POST"])
@login_required
def delete_chat(id):
    # Deletes an entire conversation
    conn = get_db_connection()
    conn.execute('DELETE FROM history WHERE chat_id = ? AND user_id = ?', (id, session['user_id']))
    conn.execute('DELETE FROM chats WHERE id = ? AND user_id = ?', (id, session['user_id']))
    conn.commit()
    conn.close()
    return "OK"

@app.route("/delete_all_history", methods=["POST"])
@login_required
def delete_all_history():
    # Deletes EVERYTHING (Danger Zone)
    conn = get_db_connection()
    conn.execute('DELETE FROM history WHERE user_id = ?', (session['user_id'],))
    conn.execute('DELETE FROM chats WHERE user_id = ?', (session['user_id'],))
    conn.commit()
    conn.close()
    return "OK"

# Initialize the DB when the app starts
init_db()

if __name__ == "__main__":
    # If frozen, debug must be False to avoid reloader issues
    if getattr(sys, 'frozen', False):
        # Open browser automatically
        def open_browser():
            time.sleep(1.5)
            webbrowser.open("http://127.0.0.1:5000")
        
        threading.Thread(target=open_browser).start()
        app.run(debug=False)
    else:
        app.run(debug=True)
