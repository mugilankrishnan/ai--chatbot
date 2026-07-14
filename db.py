import sqlite3

DB_PATH = "chatbot.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT DEFAULT '',
            is_verified INTEGER DEFAULT 0,
            otp TEXT,
            otp_expires_at TEXT,
            reset_otp TEXT,
            reset_otp_expires_at TEXT,
            auth_provider TEXT DEFAULT 'email',
            google_id TEXT,
            default_model TEXT DEFAULT 'llama-3.3-70b-versatile',
            system_prompt TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            topic TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shared_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            share_id TEXT UNIQUE NOT NULL,
            session_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def create_user(name, email, password, otp=None, otp_expires_at=None):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (name, email, password, otp, otp_expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, email, password, otp, otp_expires_at))
        conn.commit()
        return cursor.lastrowid
    except:
        return None
    finally:
        conn.close()

def get_user_by_email(email):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_google_id(google_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE google_id = ?", (google_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_google_user(name, email, google_id):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (name, email, password, is_verified, auth_provider, google_id)
            VALUES (?, ?, '', 1, 'google', ?)
        """, (name, email, google_id))
        conn.commit()
        return cursor.lastrowid
    except:
        return None
    finally:
        conn.close()

def link_google_id_to_user(user_id, google_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET google_id = ?, auth_provider = 'google', is_verified = 1 WHERE id = ?", (google_id, user_id))
    conn.commit()
    conn.close()

def update_user_name(user_id, name):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
    conn.commit()
    conn.close()

def update_user_password(user_id, password_hash):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password = ? WHERE id = ?", (password_hash, user_id))
    conn.commit()
    conn.close()

def update_default_model(user_id, model):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET default_model = ? WHERE id = ?", (model, user_id))
    conn.commit()
    conn.close()

def update_system_prompt(user_id, system_prompt):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET system_prompt = ? WHERE id = ?", (system_prompt, user_id))
    conn.commit()
    conn.close()

def save_message(session_id, user_id, role, content):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (session_id, user_id, role, content) VALUES (?, ?, ?, ?)",
                   (session_id, user_id, role, content))
    conn.commit()
    conn.close()

def get_history(session_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM messages WHERE session_id = ?", (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": row["role"], "content": row["content"]} for row in rows]

def delete_history(session_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM topics WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

def delete_all_history(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM topics WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_all_sessions(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT session_id FROM messages WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row["session_id"] for row in rows]

def delete_messages_after(session_id, message_content):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM messages WHERE session_id = ? AND content = ? ORDER BY id DESC LIMIT 1", (session_id, message_content))
    row = cursor.fetchone()
    if row:
        cursor.execute("DELETE FROM messages WHERE session_id = ? AND id >= ?", (session_id, row["id"]))
        conn.commit()
    conn.close()

def save_topic(session_id, user_id, topic):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO topics (session_id, user_id, topic) VALUES (?, ?, ?)", (session_id, user_id, topic))
    conn.commit()
    conn.close()

def get_all_topics(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT session_id, topic FROM topics WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return {row["session_id"]: row["topic"] for row in rows}

def save_shared_chat(share_id, session_id, user_id):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO shared_chats (share_id, session_id, user_id) VALUES (?, ?, ?)", (share_id, session_id, user_id))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_shared_chat(share_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM shared_chats WHERE share_id = ?", (share_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None