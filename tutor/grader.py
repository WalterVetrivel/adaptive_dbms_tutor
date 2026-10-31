"""Grade a student's answer to any item type. Deterministic: no LLM involved."""
from __future__ import annotations

from dataclasses import dataclass

from . import fd_tools, schedule_tools, sql_sandbox
from .schemas import Item


@dataclass
class GradeResult:
    correct: bool
    feedback: str
    expected: str                       # human-readable correct answer
    chosen_option: str | None = None    # MCQ letter
    sql_error: str = ""
    row_diff: str = ""
    student_rows: list | None = None
    student_columns: list | None = None


def grade(item: Item, answer: str) -> GradeResult:
    answer = (answer or "").strip()
    if item.type == "mcq":
        letter = answer.upper()[:1]
        ok = letter == item.answer
        exp = f"{item.answer}. {item.options[ord(item.answer) - 65]}" if item.options else item.answer
        return GradeResult(ok, "Correct." if ok else f"The correct answer is {exp}", exp, chosen_option=letter)
    if item.type == "sql":
        g = sql_sandbox.grade_sql(answer, item.reference_sql or "")
        return GradeResult(g.correct, g.feedback, item.reference_sql or "",
                           sql_error=g.student.error, row_diff="" if g.correct else g.feedback,
                           student_rows=g.student.rows[:20], student_columns=g.student.columns)
    if item.type == "fd":
        expected = fd_tools.solve(item.fd_spec or {})
        try:
            ok = fd_tools.grade(item.fd_spec or {}, answer)
        except Exception:
            ok = False
        return GradeResult(ok, "Correct." if ok else f"The correct answer is {expected}", expected)
    if item.type == "schedule":
        expected = schedule_tools.solve(item.schedule_spec or {})
        try:
            ok = schedule_tools.grade(item.schedule_spec or {}, answer)
        except Exception:
            ok = False
        return GradeResult(ok, "Correct." if ok else f"The correct answer is {expected}", expected)
    raise ValueError(f"Unknown item type {item.type}")
