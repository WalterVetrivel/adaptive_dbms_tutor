"""Elo calibration: item difficulty and per-(student, concept) ability are updated together."""
from __future__ import annotations

import sqlite3

K_ITEM = 24.0
K_STUDENT = 32.0
STUDENT_INIT = 1100.0


def expected(student_elo: float, item_elo: float) -> float:
    """Predicted probability the student answers the item correctly."""
    return 1.0 / (1.0 + 10 ** ((item_elo - student_elo) / 400.0))


def student_elo(conn: sqlite3.Connection, student_id: str, concept_id: str) -> float:
    row = conn.execute("SELECT elo FROM mastery WHERE student_id=? AND concept_id=?",
                       (student_id, concept_id)).fetchone()
    return row["elo"] if row else STUDENT_INIT


def update(conn: sqlite3.Connection, student_id: str, concept_id: str, item_id: str, correct: bool) -> tuple[float, float]:
    """Update both ratings; returns (new student elo, new item elo). Mastery row must already exist."""
    item = conn.execute("SELECT elo, n_responses FROM items WHERE id=?", (item_id,)).fetchone()
    s_elo = student_elo(conn, student_id, concept_id)
    i_elo = item["elo"]
    e = expected(s_elo, i_elo)
    score = 1.0 if correct else 0.0
    # items settle faster once they have data; new items move more
    k_item = K_ITEM * (1.5 if item["n_responses"] < 10 else 1.0)
    new_i = i_elo + k_item * (e - score)
    new_s = s_elo + K_STUDENT * (score - e)
    conn.execute("UPDATE items SET elo=?, n_responses=n_responses+1 WHERE id=?", (new_i, item_id))
    conn.execute("UPDATE mastery SET elo=? WHERE student_id=? AND concept_id=?", (new_s, student_id, concept_id))
    return new_s, new_i
