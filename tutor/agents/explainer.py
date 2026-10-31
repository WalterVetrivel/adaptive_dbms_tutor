"""Explainer agent: a short explanation aimed at the detected misconception, grounded in the notes,
plus a contrast question. Falls back to the library remediation + worked solution when offline."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from ..graph import ConceptGraph
from ..llm import LLM, LLMUnavailable
from ..orchestrator import AnswerOutcome
from ..retrieval import Chunk, NotesIndex
from ..schemas import Item


class ExplainOut(BaseModel):
    explanation: str
    contrast_question: str = ""


@dataclass
class Explanation:
    text: str
    contrast_question: str
    notes: list[Chunk]
    source: str   # llm / fallback


def _notes_for(graph: ConceptGraph, notes: NotesIndex, item: Item, mc_id: str | None) -> list[Chunk]:
    c = graph.concepts[item.concept_id]
    q = f"{c.name} {graph.misconceptions[mc_id].belief if mc_id else ''} {item.stem[:200]}"
    return notes.search(q, k=2, unit=c.unit, section_hint=c.notes_section)


def fallback(graph: ConceptGraph, item: Item, outcome: AnswerOutcome, chunks: list[Chunk]) -> Explanation:
    mc = outcome.diagnosis.misconceptions[0][0] if outcome.diagnosis.misconceptions else None
    parts = []
    if mc:
        m = graph.misconceptions[mc]
        parts.append(f"It looks like you might believe that {m.belief[0].lower() + m.belief[1:]} "
                     f"Actually: {m.remediation}")
    if item.solution:
        parts.append(item.solution)
    return Explanation(" ".join(parts) or "Compare your answer with the correct one above.", "", chunks, "fallback")


def explain(llm: LLM | None, graph: ConceptGraph, notes: NotesIndex, item: Item, answer: str, reasoning: str,
            outcome: AnswerOutcome) -> Explanation:
    mc = outcome.diagnosis.misconceptions[0][0] if outcome.diagnosis.misconceptions else None
    chunks = _notes_for(graph, notes, item, mc)
    if llm is None:
        return fallback(graph, item, outcome, chunks)
    m = graph.misconceptions.get(mc) if mc else None
    notes_txt = "\n---\n".join(ch.text[:700] for ch in chunks) or "(none)"
    user = "\n".join(filter(None, [
        f"Question: {item.stem}",
        f"Correct answer: {outcome.grade.expected}",
        f"Student answer: {answer}",
        f"Student reasoning: {reasoning or '(none)'}",
        f"Grader feedback: {outcome.grade.feedback}",
        f"Detected misconception: {m.belief} (fix: {m.remediation})" if m else
        f"Error type: {outcome.diagnosis.error_type or 'unknown'}",
        f"Worked solution: {item.solution}" if item.solution else "",
        f"Course notes:\n{notes_txt}",
    ]))
    msgs = [{"role": "system", "content": (
        "You are a friendly DBMS tutor for undergraduates. In at most 80 words, explain why the student's "
        "thinking is wrong and what the right idea is. Address the specific misconception, use the course "
        "notes' terminology, and use a tiny concrete example if it helps. Then write one short contrast "
        "question that tests the same idea differently. Reply JSON: "
        '{"explanation": "...", "contrast_question": "..."}')},
        {"role": "user", "content": user}]
    try:
        out = llm.json(msgs, ExplainOut, agent="explainer", tier="small", temperature=0.4, max_tokens=350)
        return Explanation(out.explanation, out.contrast_question, chunks, "llm")
    except LLMUnavailable:
        return fallback(graph, item, outcome, chunks)
