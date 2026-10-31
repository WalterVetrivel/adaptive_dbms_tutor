"""Class Insights agent: turns class aggregates into a short 'what to re-teach' brief for the teacher.
Cached per day; deterministic fallback when offline."""
from __future__ import annotations

import json
import sqlite3

from pydantic import BaseModel, Field

from .. import analytics, clock
from ..graph import ConceptGraph
from ..llm import LLM, LLMUnavailable


class Gap(BaseModel):
    concept: str
    why: str
    activity: str


class Watch(BaseModel):
    student: str
    reason: str


class Brief(BaseModel):
    headline: str
    gaps: list[Gap] = Field(default_factory=list)
    students_to_watch: list[Watch] = Field(default_factory=list)
    source: str = "llm"


def facts(conn: sqlite3.Connection, graph: ConceptGraph, student_ids: list[str]) -> dict:
    names = {r["id"]: r["display_name"] for r in conn.execute("SELECT id, display_name FROM students")}
    gaps = analytics.concept_gaps(conn, graph, student_ids)[:6]
    mcs = analytics.misconception_stats(conn, student_ids)[:6]
    risk = analytics.students_at_risk(conn, student_ids, 4)
    return {
        "class_size": len(student_ids),
        "weakest_concepts": [{"concept": graph.concepts[g.concept_id].name, "unit": graph.concepts[g.concept_id].unit,
                              "mean_mastery": round(g.mean, 2), "struggling": g.n_struggling,
                              "assessed": g.n_assessed} for g in gaps],
        "top_misconceptions": [{"belief": graph.misconceptions[m.misconception_id].belief,
                                "active_students": len(m.active), "suspected_students": len(m.suspected),
                                "fix": graph.misconceptions[m.misconception_id].remediation} for m in mcs],
        "students_at_risk": [{"name": names.get(s, s), "mean_mastery": round(p, 2), "active_misconceptions": n}
                             for s, p, n in risk],
    }


def fallback(f: dict) -> Brief:
    gaps = []
    for m in f["top_misconceptions"][:3]:
        gaps.append(Gap(concept=m["belief"], why=f"{m['active_students']} students hold this actively",
                        activity=m["fix"]))
    w = f["weakest_concepts"][0] if f["weakest_concepts"] else None
    headline = (f"Weakest area: {w['concept']} (Unit {w['unit']}, class mean {w['mean_mastery']:.0%})."
                if w else "Not enough data yet.")
    return Brief(headline=headline, gaps=gaps, source="fallback",
                 students_to_watch=[Watch(student=s["name"], reason=f"mean mastery {s['mean_mastery']:.0%}, "
                                          f"{s['active_misconceptions']} active misconceptions")
                                    for s in f["students_at_risk"][:3]])


def brief(conn: sqlite3.Connection, graph: ConceptGraph, llm: LLM | None, student_ids: list[str],
          refresh: bool = False) -> Brief:
    f = facts(conn, graph, student_ids)
    if llm is None:
        return fallback(f)
    key = f"brief:{clock.now(conn).date()}:{len(student_ids)}"
    row = conn.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
    if row and not refresh:
        return Brief.model_validate_json(row["value"])
    msgs = [{"role": "system", "content": (
        "You are an experienced DBMS lecturer's teaching assistant. From the class data, write a brief for "
        "next class: a one-sentence headline, the top 3 gaps to re-teach (each: concept, why it matters from "
        "the data, one concrete 10-minute classroom activity), and up to 3 students to check in with and why. "
        "Be specific and practical. Reply JSON: {\"headline\": str, \"gaps\": [{\"concept\", \"why\", "
        "\"activity\"}], \"students_to_watch\": [{\"student\", \"reason\"}]}")},
        {"role": "user", "content": json.dumps(f)}]
    try:
        out = llm.json(msgs, Brief, agent="class_insights", tier="large", temperature=0.4, max_tokens=900)
    except LLMUnavailable:
        return fallback(f)
    out.source = "llm"
    conn.execute("INSERT OR REPLACE INTO app_state(key, value) VALUES (?,?)", (key, out.model_dump_json()))
    conn.commit()
    return out
