"""Misconception Analyst agent: reads the student's REASONING (and their SQL, the error message and
the result diff) and decides which known misconception, if any, explains the mistake.

Rule hits are passed in as hints. Strong rule hits (>= 0.9) are kept even if the model disagrees.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..grader import GradeResult
from ..graph import ConceptGraph
from ..llm import LLM
from ..orchestrator import Diagnosis
from ..schemas import Item


class Match(BaseModel):
    id: str
    confidence: float = Field(ge=0, le=1)


class AnalystOut(BaseModel):
    matches: list[Match] = Field(default_factory=list)
    error_type: Literal["conceptual", "syntax", "careless", "misread", "none"] = "none"
    rationale: str = ""
    flawed_reasoning: bool = False


SYSTEM = """You diagnose undergraduate Database Management Systems students' errors.
Judge the student's REASONING and their submitted answer, not only whether the final answer is right.
Pick misconceptions ONLY from the candidate list, and only when the evidence supports it.
If the mistake is a typo, a syntax slip, or a misread question, say so instead of forcing a misconception.
For a CORRECT answer, set flawed_reasoning=true only if the explanation reveals a wrong belief.
Reply with JSON: {"matches":[{"id":"MC-...","confidence":0.0-1.0}],
"error_type":"conceptual|syntax|careless|misread|none","rationale":"one sentence","flawed_reasoning":false}"""


def candidates(graph: ConceptGraph, item: Item, rule_hits: list[tuple[str, float]]) -> list[str]:
    ids = list(graph.concepts[item.concept_id].misconceptions)
    for mc in [item.target_misconception, *item.misconception_map.values(), *[m for m, _ in rule_hits]]:
        if mc and mc not in ids and mc in graph.misconceptions:
            ids.append(mc)
    return ids


def build_messages(graph: ConceptGraph, item: Item, answer: str, reasoning: str, result: GradeResult,
                   rule_hits: list[tuple[str, float]]) -> list[dict[str, str]]:
    cands = candidates(graph, item, rule_hits)
    lines = [f"Concept: {graph.concepts[item.concept_id].name}", f"Question: {item.stem}"]
    if item.options:
        lines.append("Options:\n" + "\n".join(f"{l}. {o}" for l, o in zip("ABCD", item.options)))
    lines.append(f"Correct answer: {result.expected}")
    if item.solution:
        lines.append(f"Worked solution: {item.solution}")
    lines.append(f"Student answer: {answer or '(blank)'}")
    lines.append(f"Student reasoning: {reasoning or '(none given)'}")
    lines.append(f"Graded: {'CORRECT' if result.correct else 'WRONG'}")
    if result.sql_error:
        lines.append(f"SQL error: {result.sql_error}")
    elif result.row_diff:
        lines.append(f"Result comparison: {result.row_diff}")
    if rule_hits:
        lines.append("Pattern-matcher hints: " + ", ".join(f"{m} ({c:.2f})" for m, c in rule_hits))
    lines.append("Candidate misconceptions:\n" + "\n".join(
        f"- {m}: {graph.misconceptions[m].belief}" for m in cands))
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


def make_analyst(llm: LLM, graph: ConceptGraph):
    """Return a callable matching orchestrator.Analyst."""

    def analyst(item: Item, answer: str, reasoning: str, result: GradeResult,
                rule_hits: list[tuple[str, float]]) -> Diagnosis:
        msgs = build_messages(graph, item, answer, reasoning, result, rule_hits)
        out = llm.json(msgs, AnalystOut, agent="misconception_analyst", tier="large", temperature=0.1,
                       max_tokens=300)
        allowed = set(candidates(graph, item, rule_hits))
        merged: dict[str, float] = {m.id: m.confidence for m in out.matches if m.id in allowed}
        for mc, conf in rule_hits:
            if conf >= 0.9:
                merged[mc] = max(conf, merged.get(mc, 0))
        if result.correct and not out.flawed_reasoning:
            merged = {}
        return Diagnosis(misconceptions=sorted(merged.items(), key=lambda kv: -kv[1]),
                         error_type="" if out.error_type == "none" else out.error_type,
                         rationale=out.rationale, flawed_reasoning=result.correct and out.flawed_reasoning,
                         source="llm")

    return analyst
