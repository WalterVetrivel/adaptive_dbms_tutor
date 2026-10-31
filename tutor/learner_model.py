"""Learner model: Bayesian Knowledge Tracing per (student, concept), modulated by item difficulty
and reasoning quality, with damped one-hop propagation along the concept graph.

Every change is written to mastery_events with its cause, so the UI can explain any value.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from .clock import iso
from .graph import ConceptGraph

P_INIT = 0.3
P_LEARN = 0.15
BASE_SLIP = 0.10
BASE_GUESS = {"mcq": 0.25, "sql": 0.05, "fd": 0.08, "schedule": 0.3}   # yes/no schedule items are guessable
BAND_FACTORS = {"easy": (1.3, 0.6), "medium": (1.0, 1.0), "hard": (0.6, 1.5)}   # (guess x, slip x)
PROPAGATE_DOWN = 0.3     # share of a drop passed to each prerequisite
PROPAGATE_UP = 0.1       # share of a gain passed to each dependant
P_MIN, P_MAX = 0.02, 0.98


def params(item_type: str, band: str) -> tuple[float, float]:
    g_x, s_x = BAND_FACTORS[band]
    guess = min(0.45, BASE_GUESS.get(item_type, 0.2) * g_x)
    slip = min(0.3, BASE_SLIP * s_x)
    return guess, slip


def bkt_posterior(p: float, correct: bool, guess: float, slip: float) -> float:
    if correct:
        return p * (1 - slip) / (p * (1 - slip) + (1 - p) * guess)
    return p * slip / (p * slip + (1 - p) * (1 - guess))


def bkt_update(p: float, correct: bool, guess: float, slip: float, partial: bool = False) -> float:
    """Observation update then learning transition. `partial` = correct answer with flawed reasoning:
    blend the correct and incorrect posteriors equally."""
    if partial:
        post = 0.5 * bkt_posterior(p, True, guess, slip) + 0.5 * bkt_posterior(p, False, guess, slip)
    else:
        post = bkt_posterior(p, correct, guess, slip)
    return min(P_MAX, max(P_MIN, post + (1 - post) * P_LEARN))


@dataclass
class MasteryChange:
    concept_id: str
    before: float
    after: float
    cause: str


@dataclass
class MasteryUpdate:
    main: MasteryChange
    propagated: list[MasteryChange] = field(default_factory=list)


def get_p(conn: sqlite3.Connection, student_id: str, concept_id: str) -> float:
    row = conn.execute("SELECT p_mastery FROM mastery WHERE student_id=? AND concept_id=?",
                       (student_id, concept_id)).fetchone()
    return row["p_mastery"] if row else P_INIT


def get_all(conn: sqlite3.Connection, student_id: str, attempted_only: bool = False) -> dict[str, float]:
    sql = "SELECT concept_id, p_mastery FROM mastery WHERE student_id=?"
    if attempted_only:
        sql += " AND n_attempts > 0"
    return {r["concept_id"]: r["p_mastery"] for r in conn.execute(sql, (student_id,))}


def attempts(conn: sqlite3.Connection, student_id: str) -> dict[str, int]:
    return {r["concept_id"]: r["n_attempts"] for r in
            conn.execute("SELECT concept_id, n_attempts FROM mastery WHERE student_id=?", (student_id,))}


def _set(conn, student_id, concept_id, before, after, cause, response_id, now: datetime, attempted: bool):
    conn.execute(
        """INSERT INTO mastery(student_id, concept_id, p_mastery, n_attempts, updated_at) VALUES (?,?,?,?,?)
           ON CONFLICT(student_id, concept_id) DO UPDATE SET p_mastery=excluded.p_mastery,
             n_attempts = mastery.n_attempts + ?, updated_at=excluded.updated_at""",
        (student_id, concept_id, after, int(attempted), iso(now), int(attempted)))
    conn.execute("INSERT INTO mastery_events(student_id, concept_id, before, after, cause, response_id, created_at)"
                 " VALUES (?,?,?,?,?,?,?)", (student_id, concept_id, before, after, cause, response_id, iso(now)))


def update(conn: sqlite3.Connection, graph: ConceptGraph, student_id: str, concept_id: str, correct: bool,
           item_type: str, band: str, now: datetime, response_id: int | None = None,
           partial: bool = False) -> MasteryUpdate:
    guess, slip = params(item_type, band)
    before = get_p(conn, student_id, concept_id)
    after = bkt_update(before, correct, guess, slip, partial)
    outcome = "correct (flawed reasoning)" if partial else ("correct" if correct else "wrong")
    cause = f"{outcome} on {band} {item_type} item"
    _set(conn, student_id, concept_id, before, after, cause, response_id, now, attempted=True)
    result = MasteryUpdate(MasteryChange(concept_id, before, after, cause))

    delta = after - before
    name = graph.concepts[concept_id].name
    if delta < 0:
        for pre in graph.prereqs(concept_id):
            b = get_p(conn, student_id, pre)
            a = max(P_MIN, b + PROPAGATE_DOWN * delta)
            if a < b:
                c = f"prerequisite of '{name}', which was answered wrongly"
                _set(conn, student_id, pre, b, a, c, response_id, now, attempted=False)
                result.propagated.append(MasteryChange(pre, b, a, c))
    elif delta > 0:
        for dep in graph.dependants(concept_id):
            b = get_p(conn, student_id, dep)
            a = min(P_MAX, b + PROPAGATE_UP * delta)
            if a > b:
                c = f"builds on '{name}', which was answered correctly"
                _set(conn, student_id, dep, b, a, c, response_id, now, attempted=False)
                result.propagated.append(MasteryChange(dep, b, a, c))
    return result


def events(conn: sqlite3.Connection, student_id: str, concept_id: str | None = None, limit: int = 50):
    sql = "SELECT * FROM mastery_events WHERE student_id=?"
    args: list = [student_id]
    if concept_id:
        sql += " AND concept_id=?"
        args.append(concept_id)
    return conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, limit)).fetchall()
