import sqlite3

def init_db():
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            session_id TEXT PRIMARY KEY,
            topic TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_message(session_id, role, content):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                   (session_id, role, content))
    conn.commit()
    conn.close()

def get_history(session_id):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM messages WHERE session_id = ?",
                   (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1]} for row in rows]

def delete_history(session_id):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM topics WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

def get_all_sessions():
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT session_id FROM messages ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def delete_messages_after(session_id, message_content):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM messages WHERE session_id = ? AND content = ? ORDER BY id DESC LIMIT 1", (session_id, message_content))
    row = cursor.fetchone()
    if row:
        cursor.execute("DELETE FROM messages WHERE session_id = ? AND id >= ?", (session_id, row[0]))
        conn.commit()
    conn.close()

def save_topic(session_id, topic):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO topics (session_id, topic) VALUES (?, ?)", (session_id, topic))
    conn.commit()
    conn.close()

def get_all_topics():
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT session_id, topic FROM topics")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}