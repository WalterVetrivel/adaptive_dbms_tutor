"""First-login placement check (2 questions per unit) and the personal study plan built from it."""
from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass

import networkx as nx

from . import clock, item_bank, learner_model, scheduler
from .graph import ConceptGraph
from .schemas import Item

QUESTIONS_PER_UNIT = 2
PLAN_SIZE = 8
MASTERED = 0.7
TYPE_PREFERENCE = ("mcq", "fd", "schedule", "sql")   # quickest to answer first: this is a placement check


# ---- status ----------------------------------------------------------------------
def status(conn: sqlite3.Connection, student_id: str) -> str | None:
    """'completed', 'skipped', or None if the student hasn't done (or skipped) the placement check."""
    row = conn.execute("SELECT status FROM onboarding WHERE student_id=?", (student_id,)).fetchone()
    return row["status"] if row else None


def needs_onboarding(conn: sqlite3.Connection, student_id: str) -> bool:
    return status(conn, student_id) is None


def unit_scores(conn: sqlite3.Connection, student_id: str) -> dict[int, tuple[int, int]]:
    row = conn.execute("SELECT unit_scores_json FROM onboarding WHERE student_id=?", (student_id,)).fetchone()
    return {int(u): tuple(v) for u, v in json.loads(row["unit_scores_json"]).items()} if row else {}


def skip(conn: sqlite3.Connection, student_id: str) -> None:
    conn.execute("INSERT OR REPLACE INTO onboarding(student_id, status, completed_at) VALUES (?,?,?)",
                 (student_id, "skipped", clock.iso(clock.now(conn))))
    conn.commit()


# ---- choosing the questions ------------------------------------------------------
def learning_order(graph: ConceptGraph) -> list[str]:
    """Topological order that keeps units together (unit 1 first) and otherwise follows the syllabus order."""
    idx = {cid: i for i, cid in enumerate(graph.concepts)}
    return list(nx.lexicographical_topological_sort(
        graph.g, key=lambda c: f"{graph.concepts[c].unit}-{idx[c]:04d}"))


def _pick_for_concept(rows: list[sqlite3.Row], band: str) -> sqlite3.Row:
    bands = ["easy", "medium", "hard"]
    return min(rows, key=lambda r: (TYPE_PREFERENCE.index(r["type"]) if r["type"] in TYPE_PREFERENCE else 9,
                                    abs(bands.index(r["difficulty_band"]) - bands.index(band)), r["id"]))


def choose_items(conn: sqlite3.Connection, graph: ConceptGraph, student_id: str,
                 per_unit: int = QUESTIONS_PER_UNIT, attempt: int = 0) -> list[Item]:
    """`per_unit` questions per unit on different concepts: one foundational (easy), then later ones
    (medium). Prefers demo-core concepts and quick item types. Deterministic per (student, attempt)."""
    rng = random.Random(f"{student_id}:{attempt}")
    order = learning_order(graph)
    out: list[Item] = []
    for unit in graph.units:
        concepts = [c for c in order if graph.concepts[c].unit == unit and item_bank.items_for(conn, c)]
        core = [c for c in concepts if graph.concepts[c].demo_core]
        pool = core if len(core) >= per_unit else concepts
        if not pool:
            continue
        # split the unit into `per_unit` slices along the learning order and take one concept from each
        n = min(per_unit, len(pool))
        slices = [pool[i * len(pool) // n:(i + 1) * len(pool) // n] for i in range(n)]
        for i, sl in enumerate(slices):
            cid = rng.choice(sl)
            row = _pick_for_concept(item_bank.items_for(conn, cid), "easy" if i == 0 else "medium")
            out.append(item_bank.from_row(row))
    return out


def attempts_so_far(conn: sqlite3.Connection, student_id: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM responses WHERE student_id=? AND mode='onboarding'",
                        (student_id,)).fetchone()[0] // (QUESTIONS_PER_UNIT * 5)


def record_dont_know(conn: sqlite3.Connection, graph: ConceptGraph, student_id: str, item: Item) -> None:
    """'I don't know' counts as a wrong answer for the learner model, without misconception evidence."""
    now = clock.now(conn)
    cur = conn.execute("INSERT INTO responses(student_id, item_id, mode, answer, reasoning, correct, created_at)"
                       " VALUES (?,?,?,?,?,0,?)", (student_id, item.id, "onboarding", None, "I don't know",
                                                   clock.iso(now)))
    learner_model.update(conn, graph, student_id, item.concept_id, False, item.type, item.difficulty_band, now,
                         cur.lastrowid)
    scheduler.review(conn, student_id, item.concept_id, scheduler.rating_for(False), now)
    conn.commit()


# ---- the study plan --------------------------------------------------------------
@dataclass
class PlanStep:
    position: int
    concept_id: str
    reason: str
    mastery: float
    attempted: bool

    @property
    def done(self) -> bool:
        return self.attempted and self.mastery >= MASTERED


def build_plan(conn: sqlite3.Connection, graph: ConceptGraph, student_id: str,
               results: list[tuple[str, bool]], size: int = PLAN_SIZE) -> list[tuple[str, str]]:
    """results = [(concept_id, correct)] from the placement check. Returns [(concept_id, reason)] in the order
    to study them: foundations first.

    1. Concepts answered wrongly, plus their shaky direct prerequisites.
    2. Demo-core concepts in units that scored below full marks (more of them for weaker units).
    3. If nothing is weak, stretch goals: unassessed demo-core concepts from each unit.
    """
    have_items = {c for c in graph.concepts if item_bank.items_for(conn, c)}
    mastery = learner_model.get_all(conn, student_id)
    correct_ids = {c for c, ok in results if ok}
    wrong = [c for c, ok in results if not ok]
    reasons: dict[str, tuple[int, str]] = {}

    def add(cid: str, tier: int, reason: str) -> None:
        if cid in have_items and cid not in correct_ids and (cid not in reasons or reasons[cid][0] > tier):
            reasons[cid] = (tier, reason)

    for cid in wrong:
        add(cid, 1, "You missed this one in the placement check")
        for pre in graph.prereqs(cid):
            if mastery.get(pre, learner_model.P_INIT) < MASTERED:
                add(pre, 1, f"Comes before *{graph.concepts[cid].name}*, which you missed")

    by_unit: dict[int, list[bool]] = {}
    for cid, ok in results:
        by_unit.setdefault(graph.concepts[cid].unit, []).append(ok)
    order = learning_order(graph)
    for unit, oks in by_unit.items():
        missed = len(oks) - sum(oks)
        if not missed:
            continue
        extra = [c for c in order if graph.concepts[c].unit == unit and graph.concepts[c].demo_core
                 and c not in reasons and c not in correct_ids]
        for cid in extra[: 2 * missed]:
            add(cid, 2, f"Unit {unit} scored {sum(oks)}/{len(oks)}: a core topic to build up")

    if not reasons:
        for unit in graph.units:
            extra = [c for c in order if graph.concepts[c].unit == unit and graph.concepts[c].demo_core
                     and c not in correct_ids and c in have_items]
            if extra:
                add(extra[-1], 3, f"You did well in Unit {unit}: a stretch topic")

    pos = {c: i for i, c in enumerate(order)}
    ranked = sorted(reasons, key=lambda c: (reasons[c][0], pos[c]))[:size]   # missed topics always make the cut
    ranked.sort(key=pos.get)     # within the plan, always study foundations before what builds on them
    return [(c, reasons[c][1]) for c in ranked]


def complete(conn: sqlite3.Connection, graph: ConceptGraph, student_id: str,
             results: list[tuple[str, bool]]) -> list[tuple[str, str]]:
    """Store the unit scores and the study plan for a finished placement check."""
    scores: dict[int, list[int]] = {}
    for cid, ok in results:
        s = scores.setdefault(graph.concepts[cid].unit, [0, 0])
        s[0] += int(ok)
        s[1] += 1
    plan = build_plan(conn, graph, student_id, results)
    conn.execute("INSERT OR REPLACE INTO onboarding(student_id, status, unit_scores_json, completed_at)"
                 " VALUES (?,?,?,?)", (student_id, "completed", json.dumps(scores), clock.iso(clock.now(conn))))
    conn.execute("DELETE FROM study_plan WHERE student_id=?", (student_id,))
    conn.executemany("INSERT INTO study_plan(student_id, position, concept_id, reason) VALUES (?,?,?,?)",
                     [(student_id, i, c, r) for i, (c, r) in enumerate(plan)])
    conn.commit()
    return plan


def plan(conn: sqlite3.Connection, student_id: str) -> list[PlanStep]:
    """The stored study plan with live mastery, so steps tick off as the student practises."""
    rows = conn.execute("SELECT s.position, s.concept_id, s.reason, m.p_mastery, m.n_attempts FROM study_plan s "
                        "LEFT JOIN mastery m ON m.student_id=s.student_id AND m.concept_id=s.concept_id "
                        "WHERE s.student_id=? ORDER BY s.position", (student_id,)).fetchall()
    return [PlanStep(r["position"], r["concept_id"], r["reason"],
                     r["p_mastery"] if r["p_mastery"] is not None else learner_model.P_INIT,
                     bool(r["n_attempts"])) for r in rows]


def open_steps(conn: sqlite3.Connection, student_id: str) -> list[str]:
    return [s.concept_id for s in plan(conn, student_id) if not s.done]
