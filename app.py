from flask import Flask, render_template, request, session, redirect, url_for, flash
from deep_translator import GoogleTranslator
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import g4f
from pytgpt.phind import PHIND

app = Flask(__name__)
app.secret_key = 'crab_secret_key_123' # Change this in production

# Use absolute path for database file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database setup
DB_PATH = os.path.join(BASE_DIR, 'database.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT UNIQUE NOT NULL, 
                  password_hash TEXT NOT NULL)''')
    # Chats table
    c.execute('''CREATE TABLE IF NOT EXISTS chats 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER,
                  title TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    # History table with user_id and chat_id
    c.execute('''CREATE TABLE IF NOT EXISTS history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER,
                  chat_id INTEGER,
                  query TEXT, 
                  result TEXT, 
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id),
                  FOREIGN KEY (chat_id) REFERENCES chats (id))''')
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)  # Add timeout to prevent locks
    conn.row_factory = sqlite3.Row
    return conn

# Login Required Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # Check if it's an AJAX request
            if request.args.get('ajax') == 'true' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {"error": "Session expired. Please log in again.", "auth_error": True}, 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Global Error Handler for AJAX
@app.errorhandler(Exception)
def handle_exception(e):
    if request.args.get('ajax') == 'true' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        print(f"CRITICAL ERROR (AJAX): {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": f"Server error: {str(e)}"}, 500
    return str(e), 500

@app.route("/")
def landing():
    return render_template("home.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/portfolio")
def portfolio():
    return render_template("portfolio.html")

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
@app.route("/app/<int:chat_id>")
@login_required
def app_interface(chat_id=None):
    conn = get_db_connection()
    # Fetch all chats for the user
    chats = conn.execute('SELECT * FROM chats WHERE user_id = ? ORDER BY timestamp DESC', 
                         (session['user_id'],)).fetchall()
    
    active_chat_id = chat_id
    history = []
    
    if active_chat_id:
        history = conn.execute('SELECT * FROM history WHERE chat_id = ? ORDER BY timestamp ASC', 
                               (active_chat_id,)).fetchall()
    
    conn.close()
    return render_template("index.html", history=history, chats=chats, active_chat_id=active_chat_id)

@app.route("/new_chat")
@login_required
def new_chat():
    # Just redirect to app without a chat_id to start fresh
    return redirect(url_for('app_interface'))

@app.route("/translate", methods=['POST'])
@login_required
def translate():
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
    query = request.args.get("query")
    query = request.args.get("query")
    detailed_req = request.args.get("detailed") == "true"
    from_history = request.args.get("from_history") == "true"
    is_ajax = request.args.get("ajax") == "true"
    
    result = ""
    ai_success = False

    try:
        # Fetch conversation history for context (last 5 interactions)
        conn = get_db_connection()
        past_interactions = conn.execute(
            'SELECT query, result FROM history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5',
            (session['user_id'],)
        ).fetchall()
        conn.close()

        # Build message history for AI
        messages = [
            {"role": "system", "content": "You are CRAB (Advanced Voice Intelligence System) developed by Yahya. You are helpful, professional, and slightly futuristic. Keep responses concise but informative."}
        ]
        
        # Add past context in chronological order
        for interaction in reversed(past_interactions):
            messages.append({"role": "user", "content": interaction['query']})
            messages.append({"role": "assistant", "content": interaction['result']})
            
        # Add current query
        if detailed_req:
            prompt = f"Provide a detailed explanation about: {query}"
        else:
            prompt = query
            
        messages.append({"role": "user", "content": prompt})
        
        # Try pytgpt (generally more stable)
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

        # Fallback to g4f if pytgpt failed
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
        
        if not ai_success:
            result = "I'm having trouble connecting to the AI service right now. Please try again in a moment."

    except Exception as e:
        print(f"Error in run: {e}")
        result = "An unexpected error occurred."
        ai_success = False

    # Save to history if successful and new
    history_id = None
    chat_id = request.args.get("chat_id")
    if chat_id == "null" or not chat_id: chat_id = None

    if ai_success and not from_history:
        conn = get_db_connection()
        
        # Create a new chat if none exists
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

    if is_ajax:
        return {
            "query": query,
            "result": result,
            "ai_success": ai_success,
            "history_id": history_id,
            "chat_id": chat_id
        }

    return redirect(url_for('app_interface', chat_id=chat_id))

@app.route("/delete_history/<int:id>", methods=["POST"])
@login_required
def delete_history(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM history WHERE id = ? AND user_id = ?', (id, session['user_id']))
    conn.commit()
    conn.close()
    return "OK"

@app.route("/delete_chat/<int:id>", methods=["POST"])
@login_required
def delete_chat(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM history WHERE chat_id = ? AND user_id = ?', (id, session['user_id']))
    conn.execute('DELETE FROM chats WHERE id = ? AND user_id = ?', (id, session['user_id']))
    conn.commit()
    conn.close()
    return "OK"

@app.route("/delete_all_history", methods=["POST"])
@login_required
def delete_all_history():
    conn = get_db_connection()
    conn.execute('DELETE FROM history WHERE user_id = ?', (session['user_id'],))
    conn.execute('DELETE FROM chats WHERE user_id = ?', (session['user_id'],))
    conn.commit()
    conn.close()
    return "OK"

init_db()

if __name__ == "__main__":
    app.run(debug=True)
