import json
import sqlite3

from config import DB_PATH
from utils import today

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT, sex TEXT, age INTEGER, height INTEGER, weight REAL,
    goal TEXT, level TEXT, place TEXT, equipment TEXT DEFAULT '[]',
    days INTEGER, duration INTEGER, injuries TEXT DEFAULT '',
    created TEXT,
    remind_on INTEGER DEFAULT 0, remind_days TEXT DEFAULT '[]', remind_time TEXT DEFAULT '19:00',
    last_remind TEXT, last_body_remind TEXT,
    ai_date TEXT, ai_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, created TEXT, data TEXT, active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, day_idx INTEGER, title TEXT, date TEXT
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER, user_id INTEGER, exercise TEXT, weight REAL, reps TEXT
);
CREATE TABLE IF NOT EXISTS body (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, date TEXT, weight REAL, waist REAL
);
CREATE TABLE IF NOT EXISTS technique (name TEXT PRIMARY KEY, text TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS results_user_ex ON results(user_id, exercise);
"""

PROFILE_FIELDS = ("name", "sex", "age", "height", "weight", "goal", "level", "place",
                  "equipment", "days", "duration", "injuries")


def init():
    conn.executescript(SCHEMA)
    conn.commit()


# ---------- users ----------

def _user(row) -> dict | None:
    if row is None:
        return None
    u = dict(row)
    u["equipment"] = json.loads(u["equipment"] or "[]")
    u["remind_days"] = json.loads(u["remind_days"] or "[]")
    return u


def get_user(uid: int) -> dict | None:
    return _user(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


def all_users() -> list[dict]:
    return [_user(r) for r in conn.execute("SELECT * FROM users")]


def update_user(uid: int, **fields):
    fields = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in fields.items()}
    assignments = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE users SET {assignments} WHERE id=?", (*fields.values(), uid))
    conn.commit()


def save_profile(uid: int, profile: dict):
    conn.execute("INSERT OR IGNORE INTO users (id, created) VALUES (?, ?)", (uid, today()))
    update_user(uid, **{k: profile[k] for k in PROFILE_FIELDS})


def take_ai_credit(uid: int, limit: int) -> bool:
    """Count one AI request against the user's daily limit; False if the limit is used up."""
    u = get_user(uid)
    used = u["ai_count"] if u["ai_date"] == today() else 0
    if used >= limit:
        return False
    update_user(uid, ai_date=today(), ai_count=used + 1)
    return True


# ---------- plans ----------

def save_plan(uid: int, data: dict):
    conn.execute("UPDATE plans SET active=0 WHERE user_id=?", (uid,))
    conn.execute("INSERT INTO plans (user_id, created, data) VALUES (?, ?, ?)",
                 (uid, today(), json.dumps(data, ensure_ascii=False)))
    conn.commit()


def get_plan(uid: int) -> dict | None:
    row = conn.execute("SELECT created, data FROM plans WHERE user_id=? AND active=1 ORDER BY id DESC LIMIT 1",
                       (uid,)).fetchone()
    if row is None:
        return None
    plan = json.loads(row["data"])
    plan["created"] = row["created"]
    return plan


# ---------- workout diary ----------

def create_workout(uid: int, day_idx: int, title: str) -> int:
    cur = conn.execute("INSERT INTO workouts (user_id, day_idx, title, date) VALUES (?, ?, ?, ?)",
                       (uid, day_idx, title, today()))
    conn.commit()
    return cur.lastrowid


def log_result(workout_id: int, uid: int, exercise: str, weight: float, reps: list[int]):
    conn.execute("INSERT INTO results (workout_id, user_id, exercise, weight, reps) VALUES (?, ?, ?, ?, ?)",
                 (workout_id, uid, exercise, weight, json.dumps(reps)))
    conn.commit()


def last_result(uid: int, exercise: str, exclude_workout: int | None = None) -> dict | None:
    row = conn.execute(
        "SELECT r.weight, r.reps, w.date FROM results r JOIN workouts w ON w.id = r.workout_id "
        "WHERE r.user_id=? AND r.exercise=? AND r.workout_id != ? ORDER BY r.id DESC LIMIT 1",
        (uid, exercise, exclude_workout or -1)).fetchone()
    if row is None:
        return None
    return {"weight": row["weight"], "reps": json.loads(row["reps"]), "date": row["date"]}


def best_weight(uid: int, exercise: str, exclude_workout: int) -> float | None:
    row = conn.execute("SELECT MAX(weight) FROM results WHERE user_id=? AND exercise=? AND workout_id != ?",
                       (uid, exercise, exclude_workout)).fetchone()
    return row[0]


def last_workout(uid: int) -> dict | None:
    row = conn.execute("SELECT * FROM workouts WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
    return dict(row) if row else None


def workout_dates(uid: int) -> list[str]:
    """Dates of workouts that have at least one logged exercise."""
    rows = conn.execute("SELECT w.date FROM workouts w WHERE w.user_id=? "
                        "AND EXISTS (SELECT 1 FROM results r WHERE r.workout_id = w.id)", (uid,))
    return [r[0] for r in rows]


def exercise_history(uid: int) -> dict[str, list[dict]]:
    history: dict[str, list[dict]] = {}
    rows = conn.execute("SELECT exercise, weight, reps FROM results WHERE user_id=? ORDER BY id", (uid,))
    for r in rows:
        history.setdefault(r["exercise"], []).append({"weight": r["weight"], "reps": json.loads(r["reps"])})
    return history


# ---------- body measurements ----------

def add_body(uid: int, weight: float, waist: float | None):
    conn.execute("INSERT INTO body (user_id, date, weight, waist) VALUES (?, ?, ?, ?)",
                 (uid, today(), weight, waist))
    conn.commit()


def body_history(uid: int, limit: int = 12) -> list[dict]:
    rows = conn.execute("SELECT date, weight, waist FROM body WHERE user_id=? ORDER BY id DESC LIMIT ?",
                        (uid, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


# ---------- technique cache ----------

def get_technique(name: str) -> str | None:
    row = conn.execute("SELECT text FROM technique WHERE name=?", (name,)).fetchone()
    return row[0] if row else None


def save_technique(name: str, text: str):
    conn.execute("INSERT OR REPLACE INTO technique (name, text) VALUES (?, ?)", (name, text))
    conn.commit()


# ---------- bot settings ----------

def get_setting(key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_setting(key: str, value: str):
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
