"""Persona-driven simulated students, answering through the real pipeline (rule-based diagnosis,
no LLM calls), so the teacher dashboard and item calibration have realistic data for the demo."""
from __future__ import annotations

import random
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import fd_tools, selector, students
from .graph import ConceptGraph
from .orchestrator import submit_answer
from .schemas import BAND_ELO, Item

SQL_CONCEPTS = {"sql_basic_structure", "sql_aggregates", "sql_group_by_having", "sql_joins", "sql_subqueries",
                "relational_algebra_basic", "relational_algebra_joins"}
DESIGN_CONCEPTS = {"keys", "functional_dependencies", "closure_candidate_keys", "nonloss_decomposition", "nf_1_2",
                   "nf_3", "bcnf", "integrity_constraints"}


@dataclass
class Persona:
    name: str
    base: float                                   # baseline skill
    unit_skill: dict[int, float] = field(default_factory=dict)
    concept_skill: dict[str, float] = field(default_factory=dict)
    misconceptions: tuple[str, ...] = ()

    def skill(self, graph: ConceptGraph, cid: str) -> float:
        if cid in self.concept_skill:
            return self.concept_skill[cid]
        return self.unit_skill.get(graph.concepts[cid].unit, self.base)


PERSONAS = {
    "all-rounder": Persona("all-rounder", 0.85),
    "sql-strong-design-weak": Persona("sql-strong-design-weak", 0.6, concept_skill={
        **{c: 0.9 for c in SQL_CONCEPTS}, **{c: 0.3 for c in DESIGN_CONCEPTS}}, misconceptions=("MC-NF-01", "MC-KEY-01")),
    "null-confused": Persona("null-confused", 0.6, misconceptions=("MC-NULL-01", "MC-NULL-02", "MC-NULL-03")),
    "where-having": Persona("where-having", 0.6, misconceptions=("MC-AGG-01", "MC-AGG-02", "MC-JOIN-01")),
    "normalization-weak": Persona("normalization-weak", 0.6, unit_skill={2: 0.4},
                                  misconceptions=("MC-NF-02", "MC-NF-01", "MC-FD-02", "MC-DEC-01")),
    "transactions-weak": Persona("transactions-weak", 0.65, unit_skill={3: 0.3},
                                 misconceptions=("MC-TX-01", "MC-TX-02", "MC-ISO-01", "MC-TX-04")),
    "theory-only": Persona("theory-only", 0.7, concept_skill={c: 0.35 for c in SQL_CONCEPTS},
                           misconceptions=("MC-AGG-01", "MC-JOIN-02", "MC-RA-01")),
    "struggling": Persona("struggling", 0.3, misconceptions=("MC-AGG-01", "MC-NULL-01", "MC-KEY-01", "MC-TX-01",
                                                             "MC-CAP-01", "MC-IDX-02")),
}

CLASS = [  # 25 students; MC-AGG-01 ends up held by ~9 (where-having, theory-only, struggling)
    ("Aarav S", "all-rounder"), ("Bhavya R", "where-having"), ("Charan K", "null-confused"),
    ("Dharani M", "normalization-weak"), ("Eshwar P", "transactions-weak"), ("Fathima N", "all-rounder"),
    ("Gokul V", "where-having"), ("Harini L", "sql-strong-design-weak"), ("Irfan A", "struggling"),
    ("Janani T", "theory-only"), ("Kishore B", "null-confused"), ("Lavanya G", "where-having"),
    ("Madhan R", "normalization-weak"), ("Nandhini S", "all-rounder"), ("Oviya K", "transactions-weak"),
    ("Pranav J", "theory-only"), ("Rithika D", "where-having"), ("Sabari V", "struggling"),
    ("Tharun E", "sql-strong-design-weak"), ("Uma P", "null-confused"), ("Varun C", "normalization-weak"),
    ("Yamini H", "where-having"), ("Zaid M", "transactions-weak"), ("Keerthana R", "struggling"),
    ("Logesh A", "all-rounder"),
]


def _wrong_fd(item: Item, rng: random.Random) -> str:
    ask = (item.fd_spec or {}).get("ask")
    if ask == "normal_form":
        return rng.choice([nf for nf in ("1NF", "2NF", "3NF", "BCNF") if nf != item.answer])
    if ask in ("lossless", "preserving"):
        return "no" if item.answer == "yes" else "yes"
    if ask == "closure":
        attrs = sorted(fd_tools.parse_attrs(item.answer))
        return "".join(attrs[:-1]) or "A"
    return item.answer.split(",")[0] + "Z"      # candidate keys: wrong set


def _misconceived_sql(item: Item, mc: str) -> str | None:
    """The query a student holding `mc` would write, when we can construct it from the reference."""
    ref = item.reference_sql or ""
    if mc == "MC-AGG-01":
        m = re.match(r"(?is)^(select .*? from \w+(?: \w+)?)(?: where (.*?))? (group by .*?) having (.*)$", ref)
        if m:
            where = f"{m.group(2)} AND {m.group(4)}" if m.group(2) else m.group(4)
            return f"{m.group(1)} WHERE {where} {m.group(3)}"
    return None


def respond(item: Item, persona: Persona, graph: ConceptGraph, rng: random.Random) -> tuple[str, str]:
    """Return (answer, reasoning) the persona would give."""
    targeted = set(item.misconception_map.values()) | ({item.target_misconception} - {None})
    held = [m for m in persona.misconceptions if m in targeted]
    p = persona.skill(graph, item.concept_id)
    p += (1200 - BAND_ELO[item.difficulty_band]) / 1000          # easy +0.2, hard -0.2
    if held and rng.random() < 0.85:
        mc = held[0]
        belief = graph.misconceptions[mc].belief
        if item.type == "mcq":
            letter = next(l for l, m in item.misconception_map.items() if m == mc) if mc in \
                item.misconception_map.values() else rng.choice([l for l in "ABCD" if l != item.answer])
            return letter, f"Because {belief[0].lower() + belief[1:]}"
        if item.type == "sql" and (q := _misconceived_sql(item, mc)):
            return q, "WHERE filters the rows I want"
        if item.type == "sql" and item.wrong_variants:
            return item.wrong_variants[0], "That should filter what I need"
        if item.type == "sql":
            return "SELECT 1", "not sure"
        if item.type == "fd":
            return _wrong_fd(item, rng), f"I think {belief[0].lower() + belief[1:]}"
        return ("yes" if item.answer.startswith("n") else "no"), f"I think {belief[0].lower() + belief[1:]}"
    if rng.random() < min(0.97, max(0.05, p)):
        if item.type == "mcq":
            return item.answer, "Recalled the definition"
        if item.type == "sql":
            return item.reference_sql or "", "Straightforward query"
        return item.answer, "Worked it out step by step"
    if item.type == "mcq":
        return rng.choice([l for l in "ABCD" if l != item.answer]), "Guessed"
    if item.type == "sql":
        return (rng.choice(item.wrong_variants) if item.wrong_variants else "SELECT * FROM employee"), "Not sure"
    if item.type == "fd":
        return _wrong_fd(item, rng), "Not sure"
    return ("yes" if item.answer.startswith("n") else "no"), "Guessed"


def simulate_student(conn: sqlite3.Connection, graph: ConceptGraph, sid: str, persona: Persona,
                     start: datetime, days: int, rng: random.Random) -> int:
    n = 0
    asked: list[str] = []
    last_wrong = None
    t = start
    # simulated students cover every demo-core concept once (diagnostic + first week of practice)
    for _ in range(len(graph.core_ids())):
        cid = selector.next_diagnostic_concept(graph, conn, sid, asked, last_wrong)
        if cid is None:
            break
        asked.append(cid)
        item = selector.pick_item(conn, sid, cid, rng=rng)
        if not item:
            continue
        ans, why = respond(item, persona, graph, rng)
        out = submit_answer(conn, graph, sid, item, ans, why, "diagnostic", rng.randint(15, 90) * 1000, now=t)
        last_wrong = None if out.grade.correct else cid
        t += timedelta(minutes=2)
        n += 1
    for day in range(1, days + 1):
        if rng.random() < 0.35:
            continue          # skipped a day
        t = start + timedelta(days=day, hours=rng.randint(0, 6))
        done: set[str] = set()
        for entry in selector.practice_queue(conn, graph, sid, t, size=rng.randint(4, 8)):
            item = selector.pick_item(conn, sid, entry.concept_id, exclude=done, misconception=entry.misconception,
                                      rng=rng)
            if not item:
                continue
            done.add(item.id)
            ans, why = respond(item, persona, graph, rng)
            submit_answer(conn, graph, sid, item, ans, why, "practice", rng.randint(15, 90) * 1000, now=t)
            t += timedelta(minutes=2)
            n += 1
    return n


def simulate_class(conn: sqlite3.Connection, graph: ConceptGraph, days: int = 10, seed: int = 7,
                   roster: list[tuple[str, str]] | None = None) -> dict[str, int]:
    rng = random.Random(seed)
    start = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=days + 1)
    counts = {}
    for name, persona in roster or CLASS:
        sid = "sim-" + students.slug(name)
        students.reset_progress(conn, sid)
        students.create(conn, name, persona=persona, simulated=True, student_id=sid)
        counts[sid] = simulate_student(conn, graph, sid, PERSONAS[persona], start, days, rng)
    conn.commit()
    return counts
