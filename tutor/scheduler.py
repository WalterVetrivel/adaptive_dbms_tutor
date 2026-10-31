"""Spaced repetition with FSRS: one card per (student, concept); reviews are served as fresh items."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from fsrs import Card, Rating, Scheduler

from .clock import iso

_scheduler = Scheduler(learning_steps=(), relearning_steps=(), enable_fuzzing=False, desired_retention=0.9)


def rating_for(correct: bool, partial: bool = False, used_hint: bool = False, fast: bool = False) -> Rating:
    if not correct:
        return Rating.Again
    if partial or used_hint:
        return Rating.Hard
    return Rating.Easy if fast else Rating.Good


def _load(conn: sqlite3.Connection, student_id: str, concept_id: str) -> Card | None:
    row = conn.execute("SELECT card_json FROM review_cards WHERE student_id=? AND concept_id=?",
                       (student_id, concept_id)).fetchone()
    return Card.from_dict(json.loads(row["card_json"])) if row else None


def review(conn: sqlite3.Connection, student_id: str, concept_id: str, rating: Rating, now: datetime) -> datetime:
    card = _load(conn, student_id, concept_id) or Card(due=now)
    card, _ = _scheduler.review_card(card, rating, review_datetime=now)
    conn.execute(
        """INSERT INTO review_cards(student_id, concept_id, card_json, due_at, last_grade) VALUES (?,?,?,?,?)
           ON CONFLICT(student_id, concept_id) DO UPDATE SET card_json=excluded.card_json,
             due_at=excluded.due_at, last_grade=excluded.last_grade""",
        (student_id, concept_id, json.dumps(card.to_dict()), iso(card.due), rating.name))
    return card.due


def due(conn: sqlite3.Connection, student_id: str, now: datetime) -> list[str]:
    """Concepts whose review is due, most overdue first."""
    rows = conn.execute("SELECT concept_id FROM review_cards WHERE student_id=? AND due_at<=? ORDER BY due_at",
                        (student_id, iso(now))).fetchall()
    return [r["concept_id"] for r in rows]


def next_due(conn: sqlite3.Connection, student_id: str) -> dict[str, str]:
    return {r["concept_id"]: r["due_at"] for r in
            conn.execute("SELECT concept_id, due_at FROM review_cards WHERE student_id=?", (student_id,))}


def retrievability(conn: sqlite3.Connection, student_id: str, concept_id: str, now: datetime) -> float | None:
    card = _load(conn, student_id, concept_id)
    if card is None or card.last_review is None:
        return None
    return _scheduler.get_card_retrievability(card, current_datetime=now)
