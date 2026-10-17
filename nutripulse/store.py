"""SQLite persistence for the log, profile, goals, water, exercise and daily history.

Everything is keyed by `uid`, a random private id the app keeps in the page URL, so people sharing one server do
not see each other's data. This is a convenience store, not an account system: anyone holding the link can open
that data, and a host with an ephemeral disk (such as Streamlit Community Cloud) can lose it on restart.
"""
import datetime
import json
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "state.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (uid TEXT, key TEXT, value TEXT, PRIMARY KEY (uid, key));
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL, day TEXT NOT NULL, meal TEXT NOT NULL,
    name TEXT NOT NULL, query TEXT, grams REAL NOT NULL, kcal REAL NOT NULL, protein REAL, carbs REAL, fat REAL,
    fiber REAL, sugar REAL, sodium REAL, source TEXT, fdc_id INTEGER, confidence TEXT, sample INTEGER DEFAULT 0,
    created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS entries_day ON entries (uid, day);
CREATE TABLE IF NOT EXISTS exercise (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL, day TEXT NOT NULL, name TEXT NOT NULL,
    minutes REAL NOT NULL, kcal REAL NOT NULL, sample INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS water (uid TEXT, day TEXT, ml REAL NOT NULL, sample INTEGER DEFAULT 0, PRIMARY KEY (uid, day));
CREATE TABLE IF NOT EXISTS favorites (uid TEXT, query TEXT, PRIMARY KEY (uid, query));
CREATE TABLE IF NOT EXISTS recents (uid TEXT, query TEXT, ts TEXT, PRIMARY KEY (uid, query));
CREATE TABLE IF NOT EXISTS daily (uid TEXT, day TEXT, snapshot TEXT NOT NULL, sample INTEGER DEFAULT 0, PRIMARY KEY (uid, day));
"""

ENTRY_FIELDS = ["meal", "name", "query", "grams", "kcal", "protein", "carbs", "fat", "fiber", "sugar", "sodium",
                "source", "fdc_id", "confidence"]


def db_path() -> Path:
    return Path(os.getenv("NUTRIPULSE_STATE_DB", DEFAULT_DB))


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def today() -> str:
    return datetime.date.today().isoformat()


class Store:
    def __init__(self, uid: str):
        if not uid:
            raise ValueError("uid required")
        self.uid = uid

    # ── key/value (profile, settings) ────────────────────────────────────────
    def _get(self, key, default=None):
        with _connect() as c:
            row = c.execute("SELECT value FROM kv WHERE uid=? AND key=?", (self.uid, key)).fetchone()
        return json.loads(row["value"]) if row else default

    def _set(self, key, value):
        with _connect() as c:
            c.execute("INSERT OR REPLACE INTO kv (uid, key, value) VALUES (?,?,?)", (self.uid, key, json.dumps(value)))

    def profile(self):
        """Body stats the person entered, or None. There are deliberately no default values."""
        return self._get("profile")

    def set_profile(self, profile: dict):
        self._set("profile", profile)

    def settings(self) -> dict:
        return self._get("settings", {})

    def update_settings(self, **kw) -> dict:
        s = self.settings()
        s.update(kw)
        self._set("settings", s)
        return s

    # ── food log ─────────────────────────────────────────────────────────────
    def add_entries(self, day: str, rows: list, sample: int = 0) -> list:
        ids = []
        with _connect() as c:
            for r in rows:
                cur = c.execute(
                    f"INSERT INTO entries (uid, day, {', '.join(ENTRY_FIELDS)}, sample, created) "
                    f"VALUES (?,?,{','.join('?' * len(ENTRY_FIELDS))},?,?)",
                    (self.uid, day, *[r.get(f) for f in ENTRY_FIELDS], sample, datetime.datetime.now().isoformat(timespec="seconds")))
                ids.append(cur.lastrowid)
        self.save_snapshot(day)
        return ids

    def entries(self, day: str) -> list:
        with _connect() as c:
            rows = c.execute("SELECT * FROM entries WHERE uid=? AND day=? ORDER BY id", (self.uid, day)).fetchall()
        return [dict(r) for r in rows]

    def delete_entries(self, ids: list) -> list:
        """Deletes and returns the removed rows (so the caller can offer Undo)."""
        removed, days = [], set()
        with _connect() as c:
            for i in ids:
                row = c.execute("SELECT * FROM entries WHERE uid=? AND id=?", (self.uid, i)).fetchone()
                if row:
                    removed.append(dict(row))
                    days.add(row["day"])
                    c.execute("DELETE FROM entries WHERE uid=? AND id=?", (self.uid, i))
        for d in days:
            self.save_snapshot(d)
        return removed

    def restore_entries(self, rows: list):
        for r in rows:
            self.add_entries(r["day"], [r], sample=r.get("sample", 0))

    def update_entry_grams(self, entry_id: int, grams: float):
        """Rescale one entry to a new weight, keeping its per-gram nutrition."""
        with _connect() as c:
            row = c.execute("SELECT * FROM entries WHERE uid=? AND id=?", (self.uid, entry_id)).fetchone()
            if not row or row["grams"] <= 0:
                return
            f = grams / row["grams"]
            c.execute("UPDATE entries SET grams=?, kcal=kcal*?, protein=protein*?, carbs=carbs*?, fat=fat*?, fiber=fiber*?, "
                      "sugar=sugar*?, sodium=sodium*? WHERE uid=? AND id=?", (grams, f, f, f, f, f, f, f, self.uid, entry_id))
            day = row["day"]
        self.save_snapshot(day)

    # ── exercise ─────────────────────────────────────────────────────────────
    def add_exercise(self, day, name, minutes, kcal, sample=0) -> int:
        with _connect() as c:
            cur = c.execute("INSERT INTO exercise (uid, day, name, minutes, kcal, sample) VALUES (?,?,?,?,?,?)",
                            (self.uid, day, name, minutes, kcal, sample))
        self.save_snapshot(day)
        return cur.lastrowid

    def exercises(self, day) -> list:
        with _connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM exercise WHERE uid=? AND day=? ORDER BY id", (self.uid, day))]

    def delete_exercise(self, ids: list) -> list:
        removed, days = [], set()
        with _connect() as c:
            for i in ids:
                row = c.execute("SELECT * FROM exercise WHERE uid=? AND id=?", (self.uid, i)).fetchone()
                if row:
                    removed.append(dict(row))
                    days.add(row["day"])
                    c.execute("DELETE FROM exercise WHERE uid=? AND id=?", (self.uid, i))
        for d in days:
            self.save_snapshot(d)
        return removed

    # ── water ────────────────────────────────────────────────────────────────
    def water(self, day) -> float:
        with _connect() as c:
            row = c.execute("SELECT ml FROM water WHERE uid=? AND day=?", (self.uid, day)).fetchone()
        return row["ml"] if row else 0.0

    def set_water(self, day, ml, sample=0):
        with _connect() as c:
            c.execute("INSERT OR REPLACE INTO water (uid, day, ml, sample) VALUES (?,?,?,?)", (self.uid, day, max(0.0, ml), sample))
        self.save_snapshot(day)

    def add_water(self, day, ml) -> float:
        total = max(0.0, self.water(day) + ml)
        self.set_water(day, total)
        return total

    # ── favorites / recents ──────────────────────────────────────────────────
    def favorites(self) -> list:
        with _connect() as c:
            return [r["query"] for r in c.execute("SELECT query FROM favorites WHERE uid=? ORDER BY rowid", (self.uid,))]

    def toggle_favorite(self, query: str) -> bool:
        """Returns True if the query is now a favorite."""
        with _connect() as c:
            exists = c.execute("SELECT 1 FROM favorites WHERE uid=? AND query=?", (self.uid, query)).fetchone()
            if exists:
                c.execute("DELETE FROM favorites WHERE uid=? AND query=?", (self.uid, query))
                return False
            c.execute("INSERT INTO favorites (uid, query) VALUES (?,?)", (self.uid, query))
            return True

    def push_recent(self, query: str):
        with _connect() as c:
            c.execute("INSERT OR REPLACE INTO recents (uid, query, ts) VALUES (?,?,?)",
                      (self.uid, query, datetime.datetime.now().isoformat(timespec="seconds")))

    def recents(self, n=8) -> list:
        with _connect() as c:
            return [r["query"] for r in c.execute("SELECT query FROM recents WHERE uid=? ORDER BY ts DESC, rowid DESC LIMIT ?", (self.uid, n))]

    # ── daily snapshots (saved automatically on every change) ────────────────
    def totals(self, day) -> dict:
        es, ex = self.entries(day), self.exercises(day)
        t = {k: round(sum((e[k] or 0) for e in es), 1) for k in ("kcal", "protein", "carbs", "fat", "fiber", "sugar", "sodium")}
        t.update(burned=round(sum(x["kcal"] for x in ex), 1), water_ml=self.water(day), foods=len(es))
        t["net"] = round(t["kcal"] - t["burned"], 1)
        return t

    def save_snapshot(self, day):
        goal = self.settings().get("calorie_goal")
        snap = dict(self.totals(day), day=day, goal=goal)
        with _connect() as c:
            if snap["foods"] == 0 and snap["burned"] == 0 and snap["water_ml"] == 0:
                c.execute("DELETE FROM daily WHERE uid=? AND day=? AND sample=0", (self.uid, day))
            else:
                prior = c.execute("SELECT sample FROM daily WHERE uid=? AND day=?", (self.uid, day)).fetchone()
                c.execute("INSERT OR REPLACE INTO daily (uid, day, snapshot, sample) VALUES (?,?,?,?)",
                          (self.uid, day, json.dumps(snap), prior["sample"] if prior else 0))
        return snap

    def history(self) -> list:
        with _connect() as c:
            rows = c.execute("SELECT snapshot, sample FROM daily WHERE uid=? ORDER BY day", (self.uid,)).fetchall()
        return [dict(json.loads(r["snapshot"]), sample=bool(r["sample"])) for r in rows]

    def history_for_day(self, day):
        return next((h for h in self.history() if h["day"] == day), None)

    # ── sample data ──────────────────────────────────────────────────────────
    def has_sample(self) -> bool:
        with _connect() as c:
            return bool(c.execute("SELECT 1 FROM entries WHERE uid=? AND sample=1 LIMIT 1", (self.uid,)).fetchone()
                        or c.execute("SELECT 1 FROM daily WHERE uid=? AND sample=1 LIMIT 1", (self.uid,)).fetchone())

    def load_sample_days(self, end_day: str, days: int = 7):
        """Seven illustrative days ending at end_day. Marked sample=1 so they can be removed in one tap."""
        end = datetime.date.fromisoformat(end_day)
        template = [
            ("Breakfast", "oatmeal with banana", 300, 255, 8, 48, 5, 7), ("Lunch", "chicken salad", 280, 420, 35, 18, 20, 5),
            ("Dinner", "salmon with rice", 350, 640, 38, 62, 24, 3), ("Snack", "greek yogurt", 170, 100, 17, 6, 1, 0),
        ]
        for back in range(days):
            day = (end - datetime.timedelta(days=back)).isoformat()
            scale = 0.85 + 0.06 * ((back * 5) % 5)
            rows = [dict(meal=m, name=n, query=n, grams=g, kcal=round(k * scale, 1), protein=round(p * scale, 1),
                         carbs=round(c * scale, 1), fat=round(f * scale, 1), fiber=fi, sugar=0, sodium=0, source="Sample data",
                         fdc_id=None, confidence="sample") for m, n, g, k, p, c, f, fi in template]
            self.add_entries(day, rows, sample=1)
            self.set_water(day, 1500 + 150 * (back % 4), sample=1)
            with _connect() as c:
                c.execute("UPDATE daily SET sample=1 WHERE uid=? AND day=?", (self.uid, day))

    def clear_sample(self):
        with _connect() as c:
            days = {r["day"] for r in c.execute("SELECT DISTINCT day FROM entries WHERE uid=? AND sample=1", (self.uid,))}
            c.execute("DELETE FROM entries WHERE uid=? AND sample=1", (self.uid,))
            c.execute("DELETE FROM water WHERE uid=? AND sample=1", (self.uid,))
            c.execute("DELETE FROM exercise WHERE uid=? AND sample=1", (self.uid,))
            c.execute("DELETE FROM daily WHERE uid=? AND sample=1", (self.uid,))
        for d in days:
            self.save_snapshot(d)

    def wipe_all(self):
        with _connect() as c:
            for t in ("kv", "entries", "exercise", "water", "favorites", "recents", "daily"):
                c.execute(f"DELETE FROM {t} WHERE uid=?", (self.uid,))
