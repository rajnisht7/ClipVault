import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.expanduser("~/.local/share/clipvault/history.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,         -- 'text' or 'image'
            content TEXT,               -- text content
            image_path TEXT,            -- path to saved image
            preview TEXT,               -- short preview for display
            timestamp TEXT NOT NULL,
            pinned INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def add_clip(clip_type, content=None, image_path=None, preview=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Avoid duplicate consecutive entries
    c.execute("SELECT content, image_path FROM clips ORDER BY id DESC LIMIT 1")
    last = c.fetchone()
    if last:
        if clip_type == 'text' and last[0] == content:
            conn.close()
            return
        if clip_type == 'image' and last[1] == image_path:
            conn.close()
            return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        "INSERT INTO clips (type, content, image_path, preview, timestamp) VALUES (?, ?, ?, ?, ?)",
        (clip_type, content, image_path, preview or (content[:80] if content else "📷 Image"), timestamp)
    )
    conn.commit()
    conn.close()

def get_clips(search="", limit=200):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if search:
        c.execute(
            "SELECT id, type, content, image_path, preview, timestamp, pinned FROM clips WHERE preview LIKE ? ORDER BY pinned DESC, id DESC LIMIT ?",
            (f"%{search}%", limit)
        )
    else:
        c.execute(
            "SELECT id, type, content, image_path, preview, timestamp, pinned FROM clips ORDER BY pinned DESC, id DESC LIMIT ?",
            (limit,)
        )
    rows = c.fetchall()
    conn.close()
    return rows

def toggle_pin(clip_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE clips SET pinned = 1 - pinned WHERE id = ?", (clip_id,))
    conn.commit()
    conn.close()

def delete_clip(clip_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
    conn.commit()
    conn.close()

def clear_all():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM clips WHERE pinned = 0")
    conn.commit()
    conn.close()
