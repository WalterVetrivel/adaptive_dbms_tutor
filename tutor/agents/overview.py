"""Topic Overview agent: a short, notes-grounded overview of one concept for its topic page.
Falls back to the concept description and the misconception library when offline."""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from ..graph import ConceptGraph
from ..llm import LLM, LLMUnavailable
from ..retrieval import Chunk, NotesIndex


class OverviewOut(BaseModel):
    overview: str
    key_points: list[str] = Field(default_factory=list)
    example: str = ""


@dataclass
class Overview:
    text: str
    key_points: list[str]
    example: str
    notes: list[Chunk] = field(default_factory=list)
    source: str = "fallback"   # llm / fallback


def notes_for(graph: ConceptGraph, notes: NotesIndex, concept_id: str, k: int = 2) -> list[Chunk]:
    c = graph.concepts[concept_id]
    return notes.search(f"{c.name} {c.description}", k=k, unit=c.unit, section_hint=c.notes_section)


def fallback(graph: ConceptGraph, concept_id: str, chunks: list[Chunk]) -> Overview:
    # key points stay empty offline: the page already lists the misconception library's fixes
    return Overview(graph.concepts[concept_id].description, [], "", chunks, "fallback")


def overview(llm: LLM | None, graph: ConceptGraph, notes: NotesIndex, concept_id: str) -> Overview:
    c = graph.concepts[concept_id]
    chunks = notes_for(graph, notes, concept_id)
    if llm is None:
        return fallback(graph, concept_id, chunks)
    pre = ", ".join(graph.concepts[p].name for p in graph.prereqs(concept_id)) or "(none)"
    mcs = "\n".join(f"- {m.belief} (fix: {m.remediation})" for m in graph.misconceptions_for(concept_id)) or "(none)"
    notes_txt = "\n---\n".join(ch.text[:700] for ch in chunks) or "(none)"
    msgs = [{"role": "system", "content": (
        "You are a friendly DBMS tutor for undergraduates preparing for an exam. Write a brief overview of one "
        "syllabus topic: at most 90 words, plain language, the course notes' terminology. Then 3 short key "
        "points a student must remember (use the common misconceptions to pick what trips students up), and "
        "one tiny concrete example (a few lines; SQL or a relation is fine). Reply JSON: "
        '{"overview": "...", "key_points": ["...", "...", "..."], "example": "..."}')},
        {"role": "user", "content": "\n".join([
            f"Topic: {c.name} (Unit {c.unit}: {graph.units[c.unit]}, Bloom {c.bloom})",
            f"Syllabus description: {c.description}",
            f"Builds on: {pre}",
            f"Common misconceptions:\n{mcs}",
            f"Course notes:\n{notes_txt}"])}]
    try:
        out = llm.json(msgs, OverviewOut, agent="overview", tier="small", temperature=0.2, max_tokens=450)
        return Overview(out.overview, out.key_points[:4], out.example, chunks, "llm")
    except LLMUnavailable:
        return fallback(graph, concept_id, chunks)
