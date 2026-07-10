import sqlite3
import secrets
import bcrypt

DB_NAME = "chatbot.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS topics(
            session_id TEXT PRIMARY KEY,
            user_id INTEGER,
            topic TEXT
        )
    """)

    if not column_exists(cursor, "messages", "user_id"):
        cursor.execute("ALTER TABLE messages ADD COLUMN user_id INTEGER")

    if not column_exists(cursor, "topics", "user_id"):
        cursor.execute("ALTER TABLE topics ADD COLUMN user_id INTEGER")

    if not column_exists(cursor, "users", "google_id"):
        cursor.execute("ALTER TABLE users ADD COLUMN google_id TEXT")

    if not column_exists(cursor, "users", "auth_provider"):
        cursor.execute("ALTER TABLE users ADD COLUMN auth_provider TEXT DEFAULT 'local'")

    conn.commit()
    conn.close()


def create_user(name, email, password):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users(name,email,password,auth_provider) VALUES(?,?,?,'local')",
            (name, email, password),
        )
        conn.commit()
        uid = cursor.lastrowid
        conn.close()
        return uid
    except sqlite3.IntegrityError:
        conn.close()
        return None


def get_user_by_email(email):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id,name,email,password,google_id,auth_provider FROM users WHERE email=?",
        (email,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_google_id(google_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id,name,email,password,google_id,auth_provider FROM users WHERE google_id=?",
        (google_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_google_user(name, email, google_id):
    conn = get_connection()
    cursor = conn.cursor()
    unusable_password = bcrypt.hashpw(secrets.token_hex(32).encode(), bcrypt.gensalt()).decode()
    try:
        cursor.execute(
            "INSERT INTO users(name,email,password,google_id,auth_provider) VALUES(?,?,?,?,'google')",
            (name, email, unusable_password, google_id),
        )
        conn.commit()
        uid = cursor.lastrowid
        conn.close()
        return uid
    except sqlite3.IntegrityError:
        conn.close()
        return None


def link_google_id_to_user(user_id, google_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET google_id=? WHERE id=?", (google_id, user_id))
    conn.commit()
    conn.close()


def save_message(session_id, user_id, role, content):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages(session_id,user_id,role,content) VALUES(?,?,?,?)",
        (session_id, user_id, role, content),
    )
    conn.commit()
    conn.close()


def get_history(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role,content FROM messages WHERE session_id=? ORDER BY id",
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def delete_history(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
    cursor.execute("DELETE FROM topics WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()


def get_all_sessions(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT session_id FROM messages WHERE user_id=? ORDER BY id DESC",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [r["session_id"] for r in rows]


def delete_messages_after(session_id, message):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM messages WHERE session_id=? AND content=? ORDER BY id DESC LIMIT 1",
        (session_id, message),
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            "DELETE FROM messages WHERE session_id=? AND id>=?",
            (session_id, row["id"]),
        )
        conn.commit()
    conn.close()


def save_topic(session_id, user_id, topic):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO topics(session_id,user_id,topic) VALUES(?,?,?)",
        (session_id, user_id, topic),
    )
    conn.commit()
    conn.close()


def get_all_topics(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT session_id,topic FROM topics WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return {r["session_id"]: r["topic"] for r in rows}