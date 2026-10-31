"""Run student/reference SQL safely on the read-only teaching DB and compare results.

Safety: read-only URI connection + SQLite authorizer that only allows reads +
single-statement check + 2-second timeout via a progress handler.
"""
from __future__ import annotations

import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import config

_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
if hasattr(sqlite3, "SQLITE_RECURSIVE"):
    _ALLOWED_ACTIONS.add(sqlite3.SQLITE_RECURSIVE)


@dataclass
class QueryResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    error: str = ""
    truncated: bool = False


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def check_statement(sql: str) -> str | None:
    """Return an error message if `sql` is not a single SELECT/WITH statement."""
    body = _strip_comments(sql).strip().rstrip(";").strip()
    if not body:
        return "Empty query."
    if ";" in body:
        return "Only one SQL statement is allowed."
    if not re.match(r"(?is)^\s*(select|with)\b", body):
        return "Only SELECT queries can be run on the practice database."
    return None


def run_query(sql: str, db_path: Path | None = None, timeout_s: float = 2.0, max_rows: int = 500) -> QueryResult:
    err = check_statement(sql)
    if err:
        return QueryResult(ok=False, error=err)
    path = Path(db_path or config.SAMPLE_DB_PATH)
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    deadline = time.monotonic() + timeout_s
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY)
    try:
        cur = conn.execute(_strip_comments(sql).strip().rstrip(";"))
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(max_rows + 1)
        return QueryResult(ok=True, columns=cols, rows=[tuple(r) for r in rows[:max_rows]],
                           truncated=len(rows) > max_rows)
    except sqlite3.OperationalError as e:
        msg = str(e)
        if "interrupted" in msg:
            msg = f"Query took longer than {timeout_s:.0f}s and was stopped."
        elif "not authorized" in msg:
            msg = "Only read-only SELECT queries are allowed."
        return QueryResult(ok=False, error=msg)
    except sqlite3.Error as e:
        return QueryResult(ok=False, error=str(e))
    finally:
        conn.close()


def _norm(v):
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, str):
        return v.strip()
    return v


def _norm_rows(rows: list[tuple]) -> list[tuple]:
    return [tuple(_norm(v) for v in r) for r in rows]


def has_order_by(sql: str) -> bool:
    return bool(re.search(r"(?is)\border\s+by\b[^)]*$", _strip_comments(sql)))


@dataclass
class SQLGrade:
    correct: bool
    student: QueryResult
    reference: QueryResult
    feedback: str
    missing_rows: int = 0
    extra_rows: int = 0


def compare(student: QueryResult, reference: QueryResult, ordered: bool) -> tuple[bool, str, int, int]:
    if not student.ok:
        return False, f"Your query failed: {student.error}", 0, 0
    if len(student.columns) != len(reference.columns):
        return (False, f"Your query returns {len(student.columns)} column(s); "
                       f"the expected result has {len(reference.columns)}.", 0, 0)
    s, r = _norm_rows(student.rows), _norm_rows(reference.rows)
    if ordered:
        if s == r:
            return True, "Correct.", 0, 0
        if Counter(s) == Counter(r):
            return False, "Right rows, wrong order. Check your ORDER BY.", 0, 0
    elif Counter(s) == Counter(r):
        return True, "Correct.", 0, 0
    missing = sum((Counter(r) - Counter(s)).values())
    extra = sum((Counter(s) - Counter(r)).values())
    parts = [f"Your query returned {len(s)} row(s); expected {len(r)}."]
    if missing:
        parts.append(f"{missing} expected row(s) are missing.")
    if extra:
        parts.append(f"{extra} row(s) should not be there.")
    if len(s) == len(r) and not missing and not extra:
        parts.append("Duplicate counts differ (DISTINCT?).")
    return False, " ".join(parts), missing, extra


def grade_sql(student_sql: str, reference_sql: str, db_path: Path | None = None) -> SQLGrade:
    ref = run_query(reference_sql, db_path)
    if not ref.ok:
        raise ValueError(f"Reference SQL failed: {ref.error}")
    stu = run_query(student_sql, db_path)
    ok, fb, missing, extra = compare(stu, ref, ordered=has_order_by(reference_sql))
    return SQLGrade(ok, stu, ref, fb, missing, extra)


def verify_sql_item(reference_sql: str, wrong_variants: list[str] | None = None,
                    db_path: Path | None = None, min_rows: int = 1, max_rows: int = 50) -> tuple[bool, str]:
    """An SQL item is servable if its reference runs, returns a sensible number of rows,
    and (when given) produces a different result from each plausible wrong query."""
    ref = run_query(reference_sql, db_path)
    if not ref.ok:
        return False, f"reference fails: {ref.error}"
    if not (min_rows <= len(ref.rows) <= max_rows):
        return False, f"reference returns {len(ref.rows)} rows (want {min_rows}-{max_rows})"
    for w in wrong_variants or []:
        wr = run_query(w, db_path)
        if wr.ok and compare(wr, ref, has_order_by(reference_sql))[0]:
            return False, f"wrong variant gives the same result: {w}"
    return True, f"executes, {len(ref.rows)} rows" + (", discriminates wrong variants" if wrong_variants else "")


def schema_text(db_path: Path | None = None) -> str:
    conn = sqlite3.connect(f"file:{Path(db_path or config.SAMPLE_DB_PATH).as_posix()}?mode=ro", uri=True)
    try:
        return "\n".join(r[0] for r in conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name"))
    finally:
        conn.close()
