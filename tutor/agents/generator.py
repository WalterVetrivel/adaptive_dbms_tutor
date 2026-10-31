"""Question Generator agent: writes items targeted at a concept, difficulty band and misconception,
grounded in the course notes. Every draft is then checked by code (verifier.py); MCQs are also
answered blind by a second model call, and discarded if it disagrees with the key."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from .. import sql_sandbox
from ..graph import ConceptGraph
from ..llm import LLM, LLMUnavailable
from ..retrieval import NotesIndex
from ..schemas import Item
from ..verifier import verify

BAND_GUIDE = {
    "easy": "Bloom L1-L2: recall or recognise one idea. One step.",
    "medium": "Bloom L3: apply the concept to a small concrete case. Two or three steps.",
    "hard": "Bloom L3-L4: combine with a prerequisite or an edge case (NULLs, multiple keys, tricky schedules).",
}

TYPE_GUIDE = {
    "mcq": ('Multiple choice with exactly 4 options and one correct answer letter A-D. Each wrong option should '
            'be what a student holding one of the listed misconceptions would pick; map those option letters to '
            'misconception ids in "misconception_map". Never tag the correct option.'),
    "sql": ('A "write the SQL" task on the sample database below. Give "reference_sql" (SQLite, single SELECT, '
            'returns 1-50 rows) and 1-2 "wrong_variants": the query a student with the target misconception '
            'would write. The wrong variants must produce a different result.'),
    "fd": ('A functional-dependency task. Give "fd_spec" = {"attributes": "ABCDE", "fds": "A->B, B->C", '
           '"ask": "closure"|"candidate_keys"|"normal_form"|"lossless"|"preserving", "of": "AB" (closure only), '
           '"decomposition": "AB, BC" (lossless/preserving only)}. Leave "answer" empty; it is computed by code.'),
    "schedule": ('A transaction-schedule task. Give "schedule_spec" = {"schedule": "r1(A) w2(A) c1 c2", '
                 '"ask": "conflict_serializable"|"serial_order"|"recoverable"|"cascadeless"}. Leave "answer" '
                 'empty; it is computed by code.'),
}


class Draft(BaseModel):
    stem: str
    options: list[str] | None = None
    answer: str = ""
    reference_sql: str | None = None
    wrong_variants: list[str] = Field(default_factory=list)
    fd_spec: dict | None = None
    schedule_spec: dict | None = None
    misconception_map: dict[str, str] = Field(default_factory=dict)
    solution: str


class CrossCheck(BaseModel):
    answer: Literal["A", "B", "C", "D"]
    ambiguous: bool = False


def build_messages(graph: ConceptGraph, notes: NotesIndex, concept_id: str, item_type: str, band: str,
                   misconception: str | None = None, avoid: list[str] | None = None) -> list[dict[str, str]]:
    c = graph.concepts[concept_id]
    mcs = graph.misconceptions_for(concept_id)
    chunks = notes.search(f"{c.name} {c.description}", k=2, unit=c.unit, section_hint=c.notes_section)
    notes_txt = "\n---\n".join(ch.text[:1200] for ch in chunks) or "(no notes available)"
    target = graph.misconceptions[misconception] if misconception else None
    parts = [
        f"Concept: {c.name} (Unit {c.unit}: {graph.units[c.unit]}). {c.description}",
        f"Difficulty: {band}. {BAND_GUIDE[band]}",
        f"Format: {TYPE_GUIDE[item_type]}",
        "Known misconceptions for this concept:\n" + "\n".join(f"- {m.id}: {m.belief}" for m in mcs),
    ]
    if target:
        parts.append(f"Target misconception: {target.id} ({target.belief}). The question must expose it.")
    if item_type == "sql":
        parts.append("Sample database schema (SQLite):\n" + sql_sandbox.schema_text())
    parts.append(f"Course notes excerpt (use its terminology):\n{notes_txt}")
    if avoid:
        parts.append("Do not repeat these existing questions:\n" + "\n".join(f"- {s[:120]}" for s in avoid[:8]))
    parts.append('Reply with JSON: {"stem", "options", "answer", "reference_sql", "wrong_variants", '
                 '"fd_spec", "schedule_spec", "misconception_map", "solution"} (use null for unused fields).')
    return [
        {"role": "system", "content": "You write exam-prep questions for an undergraduate Database Management "
                                      "Systems course (Anna University style). Be precise and unambiguous. "
                                      "Output JSON only."},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def cross_check_mcq(llm: LLM, item: Item) -> tuple[bool, str]:
    opts = "\n".join(f"{l}. {o}" for l, o in zip("ABCD", item.options or []))
    msgs = [{"role": "system", "content": "You are a DBMS expert. Answer the multiple-choice question. "
                                          'Reply JSON: {"answer": "A|B|C|D", "ambiguous": true|false}.'},
            {"role": "user", "content": f"{item.stem}\n{opts}"}]
    out = llm.json(msgs, CrossCheck, agent="mcq_cross_check", tier="small", temperature=0.0, max_tokens=60)
    if out.ambiguous:
        return False, "cross-check flagged ambiguity"
    if out.answer != item.answer:
        return False, f"cross-check answered {out.answer}, key says {item.answer}"
    return True, "cross-check agrees"


def generate_item(llm: LLM, graph: ConceptGraph, notes: NotesIndex, concept_id: str, item_type: str, band: str,
                  misconception: str | None = None, avoid: list[str] | None = None,
                  attempts: int = 2) -> tuple[Item | None, list[str]]:
    """Generate → verify (code) → cross-check (MCQ). Returns (item or None, log of rejections)."""
    log: list[str] = []
    for attempt in range(attempts):
        msgs = build_messages(graph, notes, concept_id, item_type, band, misconception, avoid)
        if attempt:
            msgs[-1]["content"] += f"\n\nYour previous attempt was rejected: {log[-1]}. Fix that."
        try:
            draft = llm.json(msgs, Draft, agent="generator", tier="large", temperature=0.7, max_tokens=1500)
        except LLMUnavailable as e:
            log.append(f"llm: {e}")
            break
        data = draft.model_dump()
        if isinstance(data.get("answer"), str):
            data["answer"] = data["answer"].strip().upper()[:1] if item_type == "mcq" else data["answer"]
        item = Item(concept_id=concept_id, type=item_type, difficulty_band=band,
                    target_misconception=misconception, source="generated",
                    **{k: v for k, v in data.items() if v is not None}).ensure_id()
        ok, note = verify(item, graph)
        if ok and item.type == "mcq":
            try:
                ok, note2 = cross_check_mcq(llm, item)
                note = f"{note}; {note2}"
                item.verification_note = note
                item.verified = ok
            except LLMUnavailable as e:
                ok, note = False, f"cross-check unavailable: {e}"
        if ok:
            return item, log
        log.append(note)
    return None, log


def draft_json_example() -> str:
    return json.dumps(Draft(stem="...", solution="...").model_dump(), indent=2)
