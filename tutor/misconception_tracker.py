"""Per-student misconception state: suspected -> active -> resolved."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from .clock import iso

ACTIVE_CONFIDENCE = 0.7
ACTIVE_OCCURRENCES = 2
REPEAT_MIN_CONFIDENCE = 0.5   # weak evidence (e.g. a wrong answer on a targeting item) never activates alone
RESOLVE_AFTER_CORRECT = 2


def record_evidence(conn: sqlite3.Connection, student_id: str, mc_id: str, confidence: float,
                    response_id: int | None, now: datetime) -> str:
    row = conn.execute("SELECT * FROM student_misconceptions WHERE student_id=? AND misconception_id=?",
                       (student_id, mc_id)).fetchone()
    if row:
        occ = row["occurrences"] + 1
        conf = max(row["confidence"], confidence)
        evidence = json.loads(row["evidence_json"]) + ([response_id] if response_id else [])
    else:
        occ, conf, evidence = 1, confidence, [response_id] if response_id else []
    status = "active" if conf >= ACTIVE_CONFIDENCE or (occ >= ACTIVE_OCCURRENCES and conf >= REPEAT_MIN_CONFIDENCE) \
        else "suspected"
    conn.execute(
        """INSERT INTO student_misconceptions(student_id, misconception_id, status, confidence, occurrences,
               correct_since, evidence_json, updated_at) VALUES (?,?,?,?,?,0,?,?)
           ON CONFLICT(student_id, misconception_id) DO UPDATE SET status=excluded.status,
               confidence=excluded.confidence, occurrences=excluded.occurrences, correct_since=0,
               evidence_json=excluded.evidence_json, updated_at=excluded.updated_at""",
        (student_id, mc_id, status, conf, occ, json.dumps(evidence[-20:]), iso(now)))
    return status


def record_correct(conn: sqlite3.Connection, student_id: str, mc_ids: list[str], now: datetime) -> list[str]:
    """A correct answer (with sound reasoning) on an item that targets these misconceptions."""
    resolved = []
    for mc in mc_ids:
        row = conn.execute("SELECT status, correct_since FROM student_misconceptions WHERE student_id=? AND "
                           "misconception_id=?", (student_id, mc)).fetchone()
        if not row or row["status"] == "resolved":
            continue
        n = row["correct_since"] + 1
        status = "resolved" if n >= RESOLVE_AFTER_CORRECT else row["status"]
        conn.execute("UPDATE student_misconceptions SET correct_since=?, status=?, updated_at=? WHERE student_id=? "
                     "AND misconception_id=?", (n, status, iso(now), student_id, mc))
        if status == "resolved":
            resolved.append(mc)
    return resolved


def for_student(conn: sqlite3.Connection, student_id: str, statuses=("suspected", "active")) -> list[sqlite3.Row]:
    q = ",".join("?" * len(statuses))
    return conn.execute(f"SELECT * FROM student_misconceptions WHERE student_id=? AND status IN ({q}) "
                        "ORDER BY confidence DESC", (student_id, *statuses)).fetchall()
