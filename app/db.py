import sqlite3

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS pulses (
    boot_id TEXT NOT NULL,
    ticks   INTEGER NOT NULL,
    ts_ms   INTEGER NOT NULL,
    UNIQUE (boot_id, ticks)
);
CREATE INDEX IF NOT EXISTS idx_pulses_ts ON pulses (ts_ms);
CREATE TABLE IF NOT EXISTS uploads (
    day              TEXT PRIMARY KEY,
    strava_upload_id INTEGER,
    uploaded_at_ms   INTEGER NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def insert_pulses(rows: list[tuple[str, int, int]]) -> int:
    """Uloží impulzy (boot_id, ticks, ts_ms).

    Duplicitní záznamy (opakovaně poslaná dávka po nedoručené odpovědi)
    se díky UNIQUE constraintu tiše přeskočí. Vrací počet nově uložených.
    """
    with connect() as conn:
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO pulses (boot_id, ticks, ts_ms)"
            " VALUES (?, ?, ?)",
            rows,
        )
        return conn.total_changes - before


def pulse_timestamps() -> list[int]:
    with connect() as conn:
        cur = conn.execute("SELECT ts_ms FROM pulses ORDER BY ts_ms")
        return [row[0] for row in cur.fetchall()]


def last_pulse_ts() -> int | None:
    with connect() as conn:
        row = conn.execute("SELECT MAX(ts_ms) FROM pulses").fetchone()
        return row[0]


def pulse_timestamps_since(since_ms: int) -> list[int]:
    with connect() as conn:
        cur = conn.execute(
            "SELECT ts_ms FROM pulses WHERE ts_ms >= ? ORDER BY ts_ms",
            (since_ms,),
        )
        return [row[0] for row in cur.fetchall()]


def uploaded_days() -> set[str]:
    with connect() as conn:
        cur = conn.execute("SELECT day FROM uploads")
        return {row[0] for row in cur.fetchall()}


def mark_uploaded(day: str, strava_upload_id: int | None, now_ms: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO uploads (day, strava_upload_id, uploaded_at_ms)"
            " VALUES (?, ?, ?)",
            (day, strava_upload_id, now_ms),
        )
