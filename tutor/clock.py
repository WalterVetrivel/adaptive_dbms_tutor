"""App clock with a demo-only offset ("advance clock by N days") stored in the app DB."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone


def _offset_days(conn: sqlite3.Connection) -> float:
    row = conn.execute("SELECT value FROM app_state WHERE key='clock_offset_days'").fetchone()
    return float(row["value"]) if row else 0.0


def now(conn: sqlite3.Connection) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=_offset_days(conn))


def advance(conn: sqlite3.Connection, days: float) -> datetime:
    conn.execute("INSERT INTO app_state(key, value) VALUES ('clock_offset_days', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(_offset_days(conn) + days),))
    conn.commit()
    return now(conn)


def reset(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM app_state WHERE key='clock_offset_days'")
    conn.commit()


def offset_days(conn: sqlite3.Connection) -> float:
    return _offset_days(conn)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
