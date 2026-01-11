import sqlite3
import requests
import os

# 1. Setup DB directly
conn = sqlite3.connect('database.db')
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, result TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
cursor.execute("INSERT INTO history (query, result) VALUES ('test_delete', 'test_result')")
conn.commit()
item_id = cursor.lastrowid
print(f"Inserted item with ID: {item_id}")
conn.close()

# 2. Call Delete Route (Simulation)
# Since we can't easily run the flask app and curl it in this environment reliably if it blocks,
# I will just verify the DB function logic directly by importing the app.
# But `voice.py` has `app.run` at the bottom which runs on import if not careful,
# but it is inside `if __name__ == "__main__":` so it is safe to import.

import app
from app import app as flask_app

# Use Flask test client
with flask_app.test_client() as client:
    # Check it exists
    with app.get_db_connection() as conn:
        row = conn.execute("SELECT * FROM history WHERE id = ?", (item_id,)).fetchone()
        print(f"Before delete, Item exists: {row is not None}")

    # Delete
    response = client.post(f'/delete_history/{item_id}')
    print(f"Delete Response: {response.status_code}")

    # Check it is gone
    with app.get_db_connection() as conn:
        row = conn.execute("SELECT * FROM history WHERE id = ?", (item_id,)).fetchone()
        print(f"After delete, Item exists: {row is not None}")
