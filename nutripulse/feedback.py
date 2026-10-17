"""Local match-feedback log (SQLite). Used for future real-world metrics only:
nothing recorded here is a benchmark result until real usage exists."""
import datetime
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "feedback.sqlite"


def db_path() -> Path:
    return Path(os.getenv("NUTRIPULSE_DB", DEFAULT_DB))


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS match_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        query TEXT NOT NULL,
        source TEXT NOT NULL,
        fdc_id INTEGER,
        score REAL,
        feedback INTEGER NOT NULL CHECK (feedback IN (-1, 1)))""")
    return conn


def log_feedback(query: str, source: str, fdc_id, score, feedback: int) -> None:
    """feedback: 1 = thumbs up (match confirmed), -1 = thumbs down."""
    if feedback not in (-1, 1):
        raise ValueError("feedback must be 1 or -1")
    with _connect() as conn:
        conn.execute("INSERT INTO match_feedback (ts, query, source, fdc_id, score, feedback) VALUES (?,?,?,?,?,?)",
                     (datetime.datetime.now().isoformat(timespec="seconds"), query, source, fdc_id, score, feedback))


def summary() -> dict:
    """Counts, confirmed rate, and the most recent thumbs-down queries."""
    with _connect() as conn:
        up, down = conn.execute(
            "SELECT COALESCE(SUM(feedback = 1), 0), COALESCE(SUM(feedback = -1), 0) FROM match_feedback").fetchone()
        by_source = conn.execute(
            "SELECT source, SUM(feedback = 1), COUNT(*) FROM match_feedback GROUP BY source").fetchall()
        recent_down = conn.execute(
            "SELECT ts, query, source, fdc_id, score FROM match_feedback WHERE feedback = -1 ORDER BY id DESC LIMIT 10").fetchall()
    total = up + down
    return {"up": up, "down": down, "total": total, "confirmed_rate": (up / total) if total else None,
            "by_source": {s: {"up": u, "total": t} for s, u, t in by_source}, "recent_down": recent_down}


def _choices_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS match_choice (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, query TEXT NOT NULL, ingredient TEXT,
        original_fdc_id INTEGER, chosen_fdc_id INTEGER, chosen_rank INTEGER)""")


def log_choice(query: str, ingredient: str, original_fdc_id, chosen_fdc_id, chosen_rank: int) -> None:
    """A person replaced the app's match with another candidate. chosen_rank is 1-based in the scorer's top list.
    These rows are labelled by real use (for future evaluation), not benchmark results."""
    with _connect() as conn:
        _choices_table(conn)
        conn.execute("INSERT INTO match_choice (ts, query, ingredient, original_fdc_id, chosen_fdc_id, chosen_rank) VALUES (?,?,?,?,?,?)",
                     (datetime.datetime.now().isoformat(timespec="seconds"), query, ingredient, original_fdc_id, chosen_fdc_id, chosen_rank))


def choice_count() -> int:
    with _connect() as conn:
        _choices_table(conn)
        return conn.execute("SELECT COUNT(*) FROM match_choice").fetchone()[0]
