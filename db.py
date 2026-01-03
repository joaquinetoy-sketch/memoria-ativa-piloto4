import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_FILE = "memoria_ativa.db"

def _conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _conn()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS decks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deck_id INTEGER NOT NULL,
        prompt TEXT NOT NULL,
        answers_json TEXT NOT NULL,
        variants_json TEXT NOT NULL DEFAULT '{}',
        original TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(deck_id) REFERENCES decks(id)
    );

    CREATE TABLE IF NOT EXISTS schedules (
        card_id INTEGER PRIMARY KEY,
        due_date TEXT NOT NULL,
        interval_days REAL NOT NULL,
        ease REAL NOT NULL,
        reps INTEGER NOT NULL,
        lapses INTEGER NOT NULL,
        FOREIGN KEY(card_id) REFERENCES cards(id)
    );

    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id INTEGER NOT NULL,
        reviewed_at TEXT NOT NULL,
        rating TEXT NOT NULL,
        correct INTEGER NOT NULL,
        user_answer TEXT,
        FOREIGN KEY(card_id) REFERENCES cards(id)
    );
    """)
    conn.commit()
    conn.close()

def create_user(username: str, password_hash: str) -> bool:
    conn = _conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users(username, password_hash, created_at) VALUES(?,?,?)",
            (username, password_hash, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_user(username: str):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def create_deck(user_id: int, name: str) -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO decks(user_id, name, created_at) VALUES(?,?,?)",
        (user_id, name, datetime.now().isoformat())
    )
    deck_id = cur.lastrowid
    conn.commit()
    conn.close()
    return int(deck_id)

def list_decks(user_id: int) -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT d.*,
      (SELECT COUNT(*) FROM cards c WHERE c.deck_id=d.id) as cards_count,
      (SELECT COUNT(*) FROM schedules s JOIN cards c ON c.id=s.card_id
         WHERE c.deck_id=d.id AND datetime(s.due_date) <= datetime('now')) as due_now
    FROM decks d
    WHERE d.user_id = ?
    ORDER BY d.id DESC
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_deck(user_id: int, deck_id: int) -> bool:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM decks WHERE id = ? AND user_id = ?", (deck_id, user_id))
    if not cur.fetchone():
        conn.close()
        return False
    cur.execute("SELECT id FROM cards WHERE deck_id = ?", (deck_id,))
    card_ids = [r["id"] for r in cur.fetchall()]
    for cid in card_ids:
        cur.execute("DELETE FROM schedules WHERE card_id = ?", (cid,))
        cur.execute("DELETE FROM reviews WHERE card_id = ?", (cid,))
    cur.execute("DELETE FROM cards WHERE deck_id = ?", (deck_id,))
    cur.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
    conn.commit()
    conn.close()
    return True

def add_card(deck_id: int, prompt: str, answers: list, variants: dict, original: str) -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO cards(deck_id, prompt, answers_json, variants_json, original, created_at) VALUES(?,?,?,?,?,?)",
        (deck_id, prompt, json.dumps(answers, ensure_ascii=False), json.dumps(variants or {}, ensure_ascii=False), original, datetime.now().isoformat())
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return int(cid)

def update_variants(card_id: int, variants: dict):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE cards SET variants_json=? WHERE id=?", (json.dumps(variants or {}, ensure_ascii=False), int(card_id)))
    conn.commit()
    conn.close()

def init_schedule(card_id: int, due_date_iso: str, interval_days: float = 0.0, ease: float = 2.2, reps: int = 0, lapses: int = 0):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO schedules(card_id, due_date, interval_days, ease, reps, lapses) VALUES(?,?,?,?,?,?)",
        (card_id, due_date_iso, float(interval_days), float(ease), int(reps), int(lapses))
    )
    conn.commit()
    conn.close()

def get_due_cards(user_id: int, limit: int = 20):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT c.*, s.due_date, s.interval_days, s.ease, s.reps, s.lapses, d.name as deck_name, d.id as deck_id
    FROM cards c
    JOIN decks d ON d.id = c.deck_id
    JOIN schedules s ON s.card_id = c.id
    WHERE d.user_id = ?
      AND datetime(s.due_date) <= datetime('now')
    ORDER BY datetime(s.due_date) ASC
    LIMIT ?
    """, (user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_due_today_by_deck(user_id: int) -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT d.id as deck_id, d.name as deck_name,
      SUM(CASE WHEN datetime(s.due_date) <= datetime('now') THEN 1 ELSE 0 END) as due_now,
      SUM(CASE WHEN date(s.due_date) = date('now') THEN 1 ELSE 0 END) as due_today
    FROM decks d
    LEFT JOIN cards c ON c.deck_id = d.id
    LEFT JOIN schedules s ON s.card_id = c.id
    WHERE d.user_id = ?
    GROUP BY d.id, d.name
    ORDER BY due_now DESC, due_today DESC, d.id DESC
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_card(card_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT c.*, s.due_date, s.interval_days, s.ease, s.reps, s.lapses, d.name as deck_name
    FROM cards c
    JOIN schedules s ON s.card_id = c.id
    JOIN decks d ON d.id = c.deck_id
    WHERE c.id = ?
    """, (card_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def update_schedule(card_id: int, due_date_iso: str, interval_days: float, ease: float, reps: int, lapses: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
    UPDATE schedules
    SET due_date = ?, interval_days = ?, ease = ?, reps = ?, lapses = ?
    WHERE card_id = ?
    """, (due_date_iso, float(interval_days), float(ease), int(reps), int(lapses), int(card_id)))
    conn.commit()
    conn.close()

def add_review(card_id: int, rating: str, correct: bool, user_answer: str):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reviews(card_id, reviewed_at, rating, correct, user_answer) VALUES(?,?,?,?,?)",
        (int(card_id), datetime.now().isoformat(), rating, 1 if correct else 0, user_answer)
    )
    conn.commit()
    conn.close()

def stats(user_id: int) -> Dict[str, Any]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT
      (SELECT COUNT(*) FROM decks WHERE user_id = ?) as decks,
      (SELECT COUNT(*) FROM cards c JOIN decks d ON d.id=c.deck_id WHERE d.user_id = ?) as cards,
      (SELECT COUNT(*) FROM schedules s JOIN cards c ON c.id=s.card_id JOIN decks d ON d.id=c.deck_id
         WHERE d.user_id = ? AND datetime(s.due_date) <= datetime('now')) as due_now,
      (SELECT COUNT(*) FROM reviews r JOIN cards c ON c.id=r.card_id JOIN decks d ON d.id=c.deck_id WHERE d.user_id = ?) as reviews,
      (SELECT COALESCE(AVG(correct),0) FROM reviews r JOIN cards c ON c.id=r.card_id JOIN decks d ON d.id=c.deck_id WHERE d.user_id = ?) as avg_correct
    """, (user_id, user_id, user_id, user_id, user_id))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {"decks":0,"cards":0,"due_now":0,"reviews":0,"avg_correct":0}

def export_deck(user_id: int, deck_id: int) -> Optional[dict]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM decks WHERE id=? AND user_id=?", (deck_id, user_id))
    deck = cur.fetchone()
    if not deck:
        conn.close()
        return None
    cur.execute("SELECT * FROM cards WHERE deck_id=? ORDER BY id ASC", (deck_id,))
    cards = [dict(r) for r in cur.fetchall()]
    card_ids = [c["id"] for c in cards]
    schedules = []
    if card_ids:
        qmarks = ",".join(["?"] * len(card_ids))
        cur.execute(f"SELECT * FROM schedules WHERE card_id IN ({qmarks})", card_ids)
        schedules = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {
        "version": 2,
        "exported_at": datetime.now().isoformat(),
        "deck": dict(deck),
        "cards": cards,
        "schedules": schedules
    }

def import_deck(user_id: int, payload: dict) -> int:
    deck = payload.get("deck", {})
    name = deck.get("name", "Deck importado")
    new_deck_id = create_deck(user_id, name + " (importado)")
    old_to_new = {}
    for c in payload.get("cards", []):
        answers = json.loads(c["answers_json"]) if isinstance(c.get("answers_json"), str) else c.get("answers", [])
        variants = json.loads(c.get("variants_json", "{}")) if isinstance(c.get("variants_json"), str) else c.get("variants", {})
        new_cid = add_card(new_deck_id, c["prompt"], answers, variants, c["original"])
        old_to_new[c["id"]] = new_cid
        init_schedule(new_cid, datetime.now().isoformat(), 0.0, 2.2, 0, 0)
    for s in payload.get("schedules", []):
        old_id = s.get("card_id")
        if old_id in old_to_new:
            init_schedule(
                old_to_new[old_id],
                s.get("due_date", datetime.now().isoformat()),
                float(s.get("interval_days", 0.0)),
                float(s.get("ease", 2.2)),
                int(s.get("reps", 0)),
                int(s.get("lapses", 0)),
            )
    return new_deck_id
