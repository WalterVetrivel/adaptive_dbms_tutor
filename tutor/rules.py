"""Rule-based misconception detection. Used for MCQ distractors (always) and as the
offline / rate-limited fallback for SQL answers. The LLM analyst (Phase 4) refines this."""
from __future__ import annotations

import re

from .schemas import Item


def from_mcq(item: Item, chosen: str) -> list[tuple[str, float]]:
    mc = item.misconception_map.get(chosen.strip().upper()[:1])
    return [(mc, 0.6)] if mc else []   # one distractor pick = suspected; two = active


_SQL_RULES: list[tuple[str, str, float]] = [
    # (misconception id, regex on normalised SQL, confidence)
    ("MC-NULL-01", r"(=|<>|!=)\s*null\b", 0.9),
    ("MC-AGG-01", r"\bwhere\b(?:(?!\bgroup\s+by\b).)*\b(count|sum|avg|min|max)\s*\(", 0.9),
    ("MC-NULL-03", r"\bnot\s+in\s*\(\s*select\b", 0.6),
    ("MC-SET-01", r"\bunion\s+all\b", 0.4),
]


def _norm(sql: str) -> str:
    sql = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"\s+", " ", sql.lower()).strip()


def from_sql(student_sql: str, reference_sql: str | None = None, error: str = "") -> list[tuple[str, float]]:
    s = _norm(student_sql)
    ref = _norm(reference_sql or "")
    found: dict[str, float] = {}
    for mc, pattern, conf in _SQL_RULES:
        if re.search(pattern, s) and not re.search(pattern, ref):
            found[mc] = conf
    if "misuse of aggregate" in error.lower():
        found["MC-AGG-01"] = 0.95
    # LEFT JOIN with WHERE on the right-hand alias, when the reference filters in ON
    m = re.search(r"left (?:outer )?join (\w+)(?: as)? (\w+)?", s)
    if m and " where " in s and " where " not in ref:
        alias = m.group(2) or m.group(1)
        if re.search(rf"\bwhere\b.*\b{alias}\.", s):
            found["MC-JOIN-01"] = 0.8
    # comma join or JOIN without a condition
    if re.search(r"\bfrom \w+(?: \w+)?\s*,\s*\w+", s) and " where " not in s:
        found["MC-JOIN-02"] = 0.7
    # COUNT(*) where the reference counts a column (NULLs matter)
    if "count(*)" in s and re.search(r"count\((?!\*)[\w.]+\)", ref):
        found["MC-NULL-02"] = 0.75
    # selecting non-grouped column (SQLite allows it, standard SQL doesn't)
    g = re.search(r"select (.*?) from .* group by (.*?)(?: having| order| limit|$)", s)
    if g:
        cols = [c.strip() for c in g.group(1).split(",")]
        grouped = {c.strip() for c in g.group(2).split(",")}
        if any(c and "(" not in c and c not in grouped and c.split(".")[-1] not in
               {x.split(".")[-1] for x in grouped} for c in cols):
            found["MC-AGG-02"] = 0.8
    return sorted(found.items(), key=lambda kv: -kv[1])
