"""Class-level aggregates for the teacher dashboard."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .graph import ConceptGraph


def class_students(conn: sqlite3.Connection, include_simulated: bool = True, include_real: bool = True):
    rows = conn.execute("SELECT * FROM students ORDER BY display_name").fetchall()
    return [r for r in rows if (r["is_simulated"] and include_simulated) or (not r["is_simulated"] and include_real)]


def mastery_matrix(conn: sqlite3.Connection, student_ids: list[str], concept_ids: list[str]) -> list[list[float | None]]:
    """Rows = students, cols = concepts; None where the student hasn't attempted the concept."""
    if not student_ids:
        return []
    q = ",".join("?" * len(student_ids))
    data = {(r["student_id"], r["concept_id"]): r["p_mastery"] for r in conn.execute(
        f"SELECT student_id, concept_id, p_mastery FROM mastery WHERE n_attempts>0 AND student_id IN ({q})",
        student_ids)}
    return [[data.get((s, c)) for c in concept_ids] for s in student_ids]


@dataclass
class ConceptGap:
    concept_id: str
    mean: float
    n_assessed: int
    n_struggling: int      # mastery < 0.4


def concept_gaps(conn: sqlite3.Connection, graph: ConceptGraph, student_ids: list[str],
                 concept_ids: list[str] | None = None) -> list[ConceptGap]:
    concept_ids = concept_ids or graph.core_ids()
    m = mastery_matrix(conn, student_ids, concept_ids)
    gaps = []
    for j, cid in enumerate(concept_ids):
        vals = [row[j] for row in m if row[j] is not None]
        if vals:
            gaps.append(ConceptGap(cid, sum(vals) / len(vals), len(vals), sum(v < 0.4 for v in vals)))
    return sorted(gaps, key=lambda g: g.mean)


@dataclass
class MisconceptionStat:
    misconception_id: str
    active: list[str]
    suspected: list[str]
    resolved: list[str]


def misconception_stats(conn: sqlite3.Connection, student_ids: list[str]) -> list[MisconceptionStat]:
    if not student_ids:
        return []
    q = ",".join("?" * len(student_ids))
    stats: dict[str, MisconceptionStat] = {}
    for r in conn.execute(f"SELECT student_id, misconception_id, status FROM student_misconceptions "
                          f"WHERE student_id IN ({q})", student_ids):
        s = stats.setdefault(r["misconception_id"], MisconceptionStat(r["misconception_id"], [], [], []))
        getattr(s, r["status"]).append(r["student_id"])
    return sorted(stats.values(), key=lambda s: (-len(s.active), -len(s.suspected)))


def students_at_risk(conn: sqlite3.Connection, student_ids: list[str], limit: int = 5) -> list[tuple[str, float, int]]:
    """(student_id, mean mastery over attempted concepts, # active misconceptions), weakest first."""
    out = []
    for sid in student_ids:
        r = conn.execute("SELECT AVG(p_mastery) m FROM mastery WHERE student_id=? AND n_attempts>0", (sid,)).fetchone()
        if r["m"] is None:
            continue
        n_mc = conn.execute("SELECT COUNT(*) FROM student_misconceptions WHERE student_id=? AND status='active'",
                            (sid,)).fetchone()[0]
        out.append((sid, r["m"], n_mc))
    return sorted(out, key=lambda t: (t[1] - 0.05 * t[2]))[:limit]


def unit_means(conn: sqlite3.Connection, graph: ConceptGraph, student_ids: list[str]) -> dict[int, float]:
    out = {}
    for u in graph.units:
        cids = [c.id for c in graph.by_unit(u)]
        vals = [v for row in mastery_matrix(conn, student_ids, cids) for v in row if v is not None]
        if vals:
            out[u] = sum(vals) / len(vals)
    return out


def recent_responses(conn: sqlite3.Connection, student_id: str, limit: int = 20):
    return conn.execute(
        """SELECT r.*, i.stem, i.concept_id, i.type,
                  (SELECT group_concat(COALESCE(d.misconception_id, d.error_type), ', ') FROM diagnoses d
                    WHERE d.response_id = r.id) AS diagnosis
           FROM responses r JOIN items i ON i.id = r.item_id
           WHERE r.student_id=? ORDER BY r.id DESC LIMIT ?""", (student_id, limit)).fetchall()
