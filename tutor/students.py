"""Student records."""
from __future__ import annotations

import re
import sqlite3


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "student"


def create(conn: sqlite3.Connection, display_name: str, persona: str | None = None, simulated: bool = False,
           student_id: str | None = None) -> str:
    sid = student_id or slug(display_name)
    conn.execute("INSERT OR IGNORE INTO students(id, display_name, persona, is_simulated) VALUES (?,?,?,?)",
                 (sid, display_name, persona, int(simulated)))
    conn.commit()
    return sid


def all_students(conn: sqlite3.Connection, include_simulated: bool = True) -> list[sqlite3.Row]:
    sql = "SELECT * FROM students"
    if not include_simulated:
        sql += " WHERE is_simulated=0"
    return conn.execute(sql + " ORDER BY is_simulated, display_name").fetchall()


def get(conn: sqlite3.Connection, student_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()


def reset_progress(conn: sqlite3.Connection, student_id: str) -> None:
    for table in ("mastery", "mastery_events", "review_cards", "student_misconceptions", "onboarding",
                  "study_plan"):
        conn.execute(f"DELETE FROM {table} WHERE student_id=?", (student_id,))
    conn.execute("DELETE FROM diagnoses WHERE response_id IN (SELECT id FROM responses WHERE student_id=?)",
                 (student_id,))
    conn.execute("DELETE FROM responses WHERE student_id=?", (student_id,))
    conn.commit()
