"""Tutor orchestrator: the deterministic pipeline that runs on every answer.

grade -> store response -> learner model (BKT + propagation) -> Elo -> FSRS ->
misconception evidence (rules now; the LLM analyst plugs in via `analyst`) -> outcome for the UI.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Callable, Protocol

from . import calibration, clock, learner_model, misconception_tracker, rules, scheduler
from .grader import GradeResult, grade
from .graph import ConceptGraph
from .learner_model import MasteryUpdate
from .schemas import Item


@dataclass
class Diagnosis:
    misconceptions: list[tuple[str, float]] = field(default_factory=list)
    error_type: str = ""          # conceptual / syntax / careless / misread
    rationale: str = ""
    flawed_reasoning: bool = False   # for correct answers: right answer, wrong reason
    source: str = "rule"          # rule / llm


class Analyst(Protocol):
    def __call__(self, item: Item, answer: str, reasoning: str, result: GradeResult,
                 rule_hits: list[tuple[str, float]]) -> Diagnosis: ...


@dataclass
class AnswerOutcome:
    response_id: int
    grade: GradeResult
    mastery: MasteryUpdate
    diagnosis: Diagnosis
    next_review: str
    newly_active: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)


def rule_diagnosis(item: Item, answer: str, result: GradeResult) -> Diagnosis:
    if result.correct:
        return Diagnosis()
    if item.type == "mcq":
        hits = rules.from_mcq(item, answer)
        return Diagnosis(hits, "conceptual" if hits else "", "Chose a distractor linked to a known misconception"
                         if hits else "", source="rule")
    if item.type == "sql":
        hits = rules.from_sql(answer, item.reference_sql, result.sql_error)
        etype = "conceptual" if hits else ("syntax" if result.sql_error else "")
        return Diagnosis(hits, etype, "Matched a known wrong SQL pattern" if hits else "", source="rule")
    if item.target_misconception:
        return Diagnosis([(item.target_misconception, 0.5)], "conceptual",
                         "Wrong answer on an item built to expose this misconception", source="rule")
    return Diagnosis()


def submit_answer(conn: sqlite3.Connection, graph: ConceptGraph, student_id: str, item: Item, answer: str,
                  reasoning: str = "", mode: str = "practice", time_ms: int | None = None,
                  analyst: Analyst | None = None, used_hint: bool = False,
                  on_error: Callable[[Exception], None] | None = None) -> AnswerOutcome:
    now = clock.now(conn)
    result = grade(item, answer)
    cur = conn.execute(
        "INSERT INTO responses(student_id, item_id, mode, answer, reasoning, correct, sql_error, time_ms, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (student_id, item.id, mode, answer, reasoning, int(result.correct), result.sql_error or None, time_ms,
         clock.iso(now)))
    response_id = cur.lastrowid

    diagnosis = rule_diagnosis(item, answer, result)
    if analyst is not None and (not result.correct or reasoning.strip()):
        try:
            diagnosis = analyst(item, answer, reasoning, result, diagnosis.misconceptions)
        except Exception as e:  # never let the LLM break the answer flow
            if on_error:
                on_error(e)

    partial = result.correct and diagnosis.flawed_reasoning
    mastery = learner_model.update(conn, graph, student_id, item.concept_id, result.correct, item.type,
                                   item.difficulty_band, now, response_id, partial=partial)
    calibration.update(conn, student_id, item.concept_id, item.id, result.correct)
    fast = time_ms is not None and time_ms < 20_000
    due = scheduler.review(conn, student_id, item.concept_id,
                           scheduler.rating_for(result.correct, partial, used_hint, fast), now)

    newly_active: list[str] = []
    for mc, conf in diagnosis.misconceptions:
        if mc not in graph.misconceptions:
            continue
        before = conn.execute("SELECT status FROM student_misconceptions WHERE student_id=? AND misconception_id=?",
                              (student_id, mc)).fetchone()
        status = misconception_tracker.record_evidence(conn, student_id, mc, conf, response_id, now)
        if status == "active" and (before is None or before["status"] != "active"):
            newly_active.append(mc)
        conn.execute("INSERT INTO diagnoses(response_id, misconception_id, confidence, error_type, rationale, source)"
                     " VALUES (?,?,?,?,?,?)", (response_id, mc, conf, diagnosis.error_type, diagnosis.rationale,
                                               diagnosis.source))
    if not diagnosis.misconceptions and (diagnosis.error_type or diagnosis.flawed_reasoning):
        conn.execute("INSERT INTO diagnoses(response_id, misconception_id, confidence, error_type, rationale, source)"
                     " VALUES (?,?,?,?,?,?)", (response_id, None, None, diagnosis.error_type, diagnosis.rationale,
                                               diagnosis.source))

    resolved: list[str] = []
    if result.correct and not partial:
        targeted = set(item.misconception_map.values()) | ({item.target_misconception} - {None})
        resolved = misconception_tracker.record_correct(conn, student_id, sorted(targeted), now)
    conn.commit()
    return AnswerOutcome(response_id, result, mastery, diagnosis, clock.iso(due), newly_active, resolved)
