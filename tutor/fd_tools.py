"""Functional-dependency algorithms used to verify and grade Unit 2 design questions.

Attributes are single upper-case letters ("ABCD") or comma-separated names when
`names=True` is detected (any lowercase/multi-char token).
"""
from __future__ import annotations

import re
from itertools import combinations

FD = tuple[frozenset[str], frozenset[str]]


def parse_attrs(text: str) -> frozenset[str]:
    text = text.strip().strip("{}()")
    if re.search(r"[,\s]", text) or re.search(r"[a-z]", text):
        return frozenset(t for t in re.split(r"[,\s]+", text) if t)
    return frozenset(text)


def parse_fds(text: str) -> list[FD]:
    """'A->B, BC->DE' or 'emp_id -> name dept; dept -> mgr'."""
    fds: list[FD] = []
    sep = ";" if ";" in text else None
    parts = text.split(sep) if sep else re.split(r",\s*(?=[^,]*(?:->|→))", text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lhs, rhs = re.split(r"\s*(?:->|→)\s*", part, maxsplit=1)
        fds.append((parse_attrs(lhs), parse_attrs(rhs)))
    return fds


def fmt(attrs) -> str:
    a = sorted(attrs)
    return "".join(a) if all(len(x) == 1 for x in a) else "{" + ", ".join(a) + "}"


def closure(attrs: frozenset[str] | set[str] | str, fds: list[FD]) -> frozenset[str]:
    result = set(parse_attrs(attrs) if isinstance(attrs, str) else attrs)
    changed = True
    while changed:
        changed = False
        for lhs, rhs in fds:
            if lhs <= result and not rhs <= result:
                result |= rhs
                changed = True
    return frozenset(result)


def is_superkey(attrs, relation: frozenset[str], fds: list[FD]) -> bool:
    return relation <= closure(attrs, fds)


def candidate_keys(relation: frozenset[str], fds: list[FD]) -> list[frozenset[str]]:
    # attributes never on any RHS must be in every key; prune search with them
    rhs_all = set().union(*(r for _, r in fds)) if fds else set()
    core = frozenset(relation - rhs_all)
    others = sorted(relation - core)
    keys: list[frozenset[str]] = []
    for size in range(0, len(others) + 1):
        for combo in combinations(others, size):
            cand = core | frozenset(combo)
            if any(k <= cand for k in keys):
                continue
            if is_superkey(cand, relation, fds):
                keys.append(cand)
    return sorted(keys, key=lambda k: (len(k), fmt(k)))


def prime_attributes(relation, fds) -> frozenset[str]:
    return frozenset().union(*candidate_keys(relation, fds))


def _split_rhs(fds: list[FD]) -> list[FD]:
    return [(lhs, frozenset([a])) for lhs, rhs in fds for a in rhs if a not in lhs]


def highest_normal_form(relation: frozenset[str], fds: list[FD]) -> str:
    """Highest of 1NF/2NF/3NF/BCNF (assumes atomic values, i.e. at least 1NF)."""
    keys = candidate_keys(relation, fds)
    prime = frozenset().union(*keys)
    single = _split_rhs(fds)
    bcnf = all(is_superkey(lhs, relation, fds) for lhs, _ in single)
    if bcnf:
        return "BCNF"
    third = all(is_superkey(lhs, relation, fds) or rhs <= prime for lhs, rhs in single)
    if third:
        return "3NF"
    # 2NF: no non-prime attribute partially dependent on a candidate key
    for key in keys:
        for size in range(1, len(key)):
            for part in combinations(sorted(key), size):
                dep = closure(frozenset(part), fds) - prime - frozenset(part)
                if dep:
                    return "1NF"
    return "2NF"


def is_lossless_binary(r1: frozenset[str], r2: frozenset[str], fds: list[FD]) -> bool:
    common = r1 & r2
    c = closure(common, fds)
    return r1 <= c or r2 <= c


def preserves_dependencies(decomposition: list[frozenset[str]], fds: list[FD]) -> bool:
    """Standard polynomial test: for each X->Y, grow Z=X using closures restricted to each Ri."""
    for lhs, rhs in fds:
        z = set(lhs)
        changed = True
        while changed:
            changed = False
            for ri in decomposition:
                add = closure(frozenset(z & ri), fds) & ri
                if not add <= z:
                    z |= add
                    changed = True
        if not rhs <= z:
            return False
    return True


# ---- grading helpers ---------------------------------------------------------

def parse_key_list(text: str) -> set[frozenset[str]]:
    """'AB, AC' or '{A,B}; {A,C}' -> {{A,B},{A,C}}."""
    text = text.strip()
    if "{" in text:
        groups = re.findall(r"\{([^}]*)\}", text)
        return {parse_attrs(g) for g in groups}
    return {parse_attrs(g) for g in re.split(r"[;,/]|\band\b", text) if g.strip()}


def solve(spec: dict) -> str:
    """Compute the canonical answer for an FD item spec.

    spec = {"attributes": "ABCDE", "fds": "A->B, ...", "ask": "closure"|"candidate_keys"|"normal_form"
            |"lossless"|"preserving", "of": "AB" (closure), "decomposition": "ABC, CDE"}
    """
    rel = parse_attrs(spec["attributes"])
    fds = parse_fds(spec["fds"])
    ask = spec["ask"]
    if ask == "closure":
        return fmt(closure(spec["of"], fds))
    if ask == "candidate_keys":
        return ", ".join(fmt(k) for k in candidate_keys(rel, fds))
    if ask == "normal_form":
        return highest_normal_form(rel, fds)
    parts = [parse_attrs(p) for p in re.split(r"[;,]\s*", spec["decomposition"])]
    if ask == "lossless":
        return "yes" if is_lossless_binary(parts[0], parts[1], fds) else "no"
    if ask == "preserving":
        return "yes" if preserves_dependencies(parts, fds) else "no"
    raise ValueError(f"Unknown ask: {ask}")


def grade(spec: dict, student_answer: str) -> bool:
    expected = solve(spec)
    ask = spec["ask"]
    s = student_answer.strip()
    if ask == "closure":
        return parse_attrs(s.replace("+", "").split("=")[-1]) == parse_attrs(expected)
    if ask == "candidate_keys":
        return parse_key_list(s) == parse_key_list(expected)
    if ask == "normal_form":
        return re.sub(r"[^A-Z0-9]", "", s.upper()) == expected.upper()
    return s.lower().startswith(expected[0])
