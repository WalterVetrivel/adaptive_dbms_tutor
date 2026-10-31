"""Code-based verification of items. The LLM never decides what is correct for SQL/FD/schedule items."""
from __future__ import annotations

from . import fd_tools, schedule_tools, sql_sandbox
from .graph import ConceptGraph
from .schemas import LETTERS, Item


def verify(item: Item, graph: ConceptGraph) -> tuple[bool, str]:
    """Check an item and fill in computed answers. Returns (ok, note) and mutates item.verified/answer."""
    if item.concept_id not in graph.concepts:
        return _done(item, False, f"unknown concept {item.concept_id}")
    for mc in list(item.misconception_map.values()) + ([item.target_misconception] if item.target_misconception else []):
        if mc not in graph.misconceptions:
            return _done(item, False, f"unknown misconception {mc}")

    if item.type == "mcq":
        if not item.options or len(item.options) != 4:
            return _done(item, False, "MCQ needs 4 options")
        if item.answer not in LETTERS:
            return _done(item, False, "MCQ answer must be A-D")
        if len({o.strip().lower() for o in item.options}) != 4:
            return _done(item, False, "duplicate options")
        if item.answer in item.misconception_map:
            return _done(item, False, "correct option is tagged with a misconception")
        return _done(item, True, "structure ok")

    if item.type == "sql":
        if not item.reference_sql:
            return _done(item, False, "missing reference_sql")
        ok, note = sql_sandbox.verify_sql_item(item.reference_sql, item.wrong_variants)
        return _done(item, ok, note)

    if item.type == "fd":
        if not item.fd_spec:
            return _done(item, False, "missing fd_spec")
        try:
            computed = fd_tools.solve(item.fd_spec)
        except Exception as e:
            return _done(item, False, f"fd_spec error: {e}")
        if item.answer and not fd_tools.grade(item.fd_spec, item.answer):
            return _done(item, False, f"stated answer {item.answer!r} != computed {computed!r}")
        item.answer = computed
        return _done(item, True, f"answer computed by FD algorithm: {computed}")

    if item.type == "schedule":
        if not item.schedule_spec:
            return _done(item, False, "missing schedule_spec")
        try:
            computed = schedule_tools.solve(item.schedule_spec)
        except Exception as e:
            return _done(item, False, f"schedule_spec error: {e}")
        if item.answer and not schedule_tools.grade(item.schedule_spec, item.answer):
            return _done(item, False, f"stated answer {item.answer!r} != computed {computed!r}")
        item.answer = computed
        return _done(item, True, f"answer computed from precedence graph: {computed}")

    return _done(item, False, f"unsupported type {item.type}")


def _done(item: Item, ok: bool, note: str) -> tuple[bool, str]:
    item.verified = ok
    item.verification_note = note
    return ok, note
