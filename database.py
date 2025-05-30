import sqlite3

DB_FILE = "el_winklero.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            last_daily TEXT,
            last_worked TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # sadly needed to fix issues later down the road
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row is None:
        c.execute("INSERT INTO users(user_id, balance) VALUES (?, ?)", (user_id, 0))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_last_worked(user_id, time_str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET last_worked = ? WHERE user_id = ?", (time_str, user_id))
    conn.commit()
    conn.close()

def update_last_daily(user_id, time_str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (time_str, user_id))
    conn.commit()
    conn.close()

def update_balance(user_id: int, amount: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Ensure user exists
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    if result is None:
        # Optional: auto-create user if not exist
        c.execute("INSERT INTO users (user_id, balance, last_worked, last_daily) VALUES (?, ?, ?, ?)", (user_id, amount, "", ""))
    else:
        new_balance = result[0] + amount
        c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
    conn.commit()
    conn.close()

def update_last_flip(user_id, time_str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET last_flip = ? WHERE user_id = ?", (time_str, user_id))
    conn.commit()
    conn.close()

def get_top_users(limit=10):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def add_to_inventory(user_id, item, quantity):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO inventory(user_id, item_name, quantity) VALUES (?, ?, ?) "
              "ON CONFLICT(user_id, item_name) DO UPDATE SET quantity = quantity + ?",
              (user_id, item, quantity, quantity))
    conn.commit()
    conn.close()

def get_inventory_item(user_id, item):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT quantity FROM inventory WHERE user_id = ? AND item_name = ?", (user_id, item))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def remove_from_inventory(user_id, item, quantity):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_name = ? AND quantity >= ?",
              (quantity, user_id, item, quantity))
    conn.commit()
    conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT item_name, quantity FROM inventory WHERE user_id = ?", (user_id,))
    items = c.fetchall()
    conn.close()
    return items

