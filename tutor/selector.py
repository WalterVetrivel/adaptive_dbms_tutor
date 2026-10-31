"""Choose what to ask next: adaptive diagnostic over the concept graph, and the daily practice queue."""
from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from . import calibration, item_bank, learner_model, misconception_tracker, scheduler
from .graph import ConceptGraph
from .schemas import Item

TARGET_SUCCESS = 0.7
DIAGNOSTIC_LENGTH = 12


def uncertainty(p: float) -> float:
    return p * (1 - p)


def concepts_with_items(conn: sqlite3.Connection) -> set[str]:
    return set(item_bank.counts(conn))


def next_diagnostic_concept(graph: ConceptGraph, conn: sqlite3.Connection, student_id: str,
                            asked: list[str], last_wrong: str | None) -> str | None:
    """Prerequisites of the last wrong concept first; otherwise the most uncertain demo-core concept,
    spreading questions across units."""
    pool = [c for c in graph.core_ids() if c in concepts_with_items(conn) and c not in asked]
    if not pool:
        return None
    if last_wrong:
        pre = [p for p in graph.prereqs(last_wrong) if p in pool]
        if pre:
            return max(pre, key=lambda c: uncertainty(learner_model.get_p(conn, student_id, c)))
    asked_per_unit: dict[int, int] = {}
    for c in asked:
        u = graph.concepts[c].unit
        asked_per_unit[u] = asked_per_unit.get(u, 0) + 1
    order = {c: i for i, c in enumerate(graph.topo_order())}

    def score(c: str) -> tuple:
        p = learner_model.get_p(conn, student_id, c)
        return (-round(uncertainty(p), 3), asked_per_unit.get(graph.concepts[c].unit, 0), order[c])

    return min(pool, key=score)


def pick_item(conn: sqlite3.Connection, student_id: str, concept_id: str, exclude: set[str] | None = None,
              misconception: str | None = None, rng: random.Random | None = None) -> Item | None:
    """Item whose predicted success is closest to 70%, preferring ones that target `misconception`
    and ones the student hasn't seen."""
    rng = rng or random.Random()
    exclude = exclude or set()
    rows = item_bank.items_for(conn, concept_id)
    if not rows:
        return None
    seen = {r["item_id"] for r in conn.execute("SELECT item_id FROM responses WHERE student_id=?", (student_id,))}
    s_elo = calibration.student_elo(conn, student_id, concept_id)

    def score(r) -> tuple:
        targets = r["target_misconception"] == misconception or (
            misconception and f'"{misconception}"' in (r["misconception_map_json"] or ""))
        return (r["id"] in exclude, r["id"] in seen, not targets if misconception else False,
                round(abs(calibration.expected(s_elo, r["elo"]) - TARGET_SUCCESS), 2), rng.random())

    best = min(rows, key=score)
    if best["id"] in exclude:
        return None
    return item_bank.from_row(best)


@dataclass
class QueueEntry:
    concept_id: str
    reason: str                    # "review due" / "weak concept" / "misconception" / "new"
    misconception: str | None = None


def practice_queue(conn: sqlite3.Connection, graph: ConceptGraph, student_id: str, now: datetime,
                   size: int = 10) -> list[QueueEntry]:
    """~40% due reviews, ~40% weakest concepts, ~20% active misconceptions; topped up with
    unassessed demo-core concepts."""
    available = concepts_with_items(conn)
    queue: list[QueueEntry] = []
    used: set[str] = set()

    def add(entry: QueueEntry) -> None:
        if entry.concept_id in available and entry.concept_id not in used and len(queue) < size:
            queue.append(entry)
            used.add(entry.concept_id)

    n_mc = max(1, round(size * 0.2))
    for row in misconception_tracker.for_student(conn, student_id, ("active",))[:n_mc]:
        for cid in graph.misconceptions[row["misconception_id"]].concepts:
            if cid in available and cid not in used:
                add(QueueEntry(cid, "misconception", row["misconception_id"]))
                break
    for cid in scheduler.due(conn, student_id, now)[: round(size * 0.4)]:
        add(QueueEntry(cid, "review due"))
    attempted = learner_model.get_all(conn, student_id, attempted_only=True)
    for cid, _p in sorted(attempted.items(), key=lambda kv: kv[1]):
        if len([q for q in queue if q.reason == "weak concept"]) >= round(size * 0.4):
            break
        if _p < 0.7:
            add(QueueEntry(cid, "weak concept"))
    order = {c: i for i, c in enumerate(graph.topo_order())}
    for cid in sorted((c for c in graph.core_ids() if c not in attempted), key=order.get):
        add(QueueEntry(cid, "new"))
    return queue
