"""Transaction schedule analysis for Unit 3 questions (precedence graph, recoverability)."""
from __future__ import annotations

import re
from dataclasses import dataclass

import networkx as nx

_OP = re.compile(r"([rwc])\s*(\d+)\s*(?:\(\s*([A-Za-z]\w*)\s*\))?", re.I)


@dataclass(frozen=True)
class Op:
    kind: str   # r, w, c (commit)
    tx: int
    item: str | None


def parse_schedule(text: str) -> list[Op]:
    ops = [Op(k.lower(), int(t), i) for k, t, i in _OP.findall(text)]
    if not ops:
        raise ValueError("Could not parse schedule")
    return ops


def precedence_graph(ops: list[Op]) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from({o.tx for o in ops})
    for i, a in enumerate(ops):
        if a.kind == "c":
            continue
        for b in ops[i + 1:]:
            if b.kind == "c" or b.tx == a.tx or b.item != a.item:
                continue
            if a.kind == "w" or b.kind == "w":
                g.add_edge(a.tx, b.tx)
    return g


def conflict_serializable(ops: list[Op]) -> tuple[bool, list[int] | list[tuple[int, int]]]:
    """(True, serial order) or (False, a cycle as edge list)."""
    g = precedence_graph(ops)
    if nx.is_directed_acyclic_graph(g):
        return True, list(nx.lexicographical_topological_sort(g))
    return False, nx.find_cycle(g)


def is_recoverable(ops: list[Op]) -> bool:
    """Ti reads from Tj => Tj commits before Ti commits."""
    commit_pos = {o.tx: i for i, o in enumerate(ops) if o.kind == "c"}
    last_writer: dict[str, tuple[int, int]] = {}
    for i, o in enumerate(ops):
        if o.kind == "w":
            last_writer[o.item] = (o.tx, i)
        elif o.kind == "r" and o.item in last_writer:
            writer, _ = last_writer[o.item]
            if writer != o.tx and o.tx in commit_pos:
                if writer not in commit_pos or commit_pos[writer] > commit_pos[o.tx]:
                    return False
    return True


def is_cascadeless(ops: list[Op]) -> bool:
    """Every read reads only committed data."""
    committed: set[int] = set()
    last_writer: dict[str, int] = {}
    for o in ops:
        if o.kind == "c":
            committed.add(o.tx)
        elif o.kind == "w":
            last_writer[o.item] = o.tx
        elif o.kind == "r" and o.item in last_writer:
            w = last_writer[o.item]
            if w != o.tx and w not in committed:
                return False
    return True


def solve(spec: dict) -> str:
    """spec = {"schedule": "...", "ask": "conflict_serializable"|"serial_order"|"recoverable"|"cascadeless"}"""
    ops = parse_schedule(spec["schedule"])
    ask = spec["ask"]
    if ask == "conflict_serializable":
        return "yes" if conflict_serializable(ops)[0] else "no"
    if ask == "serial_order":
        ok, order = conflict_serializable(ops)
        return " -> ".join(f"T{t}" for t in order) if ok else "not serializable"
    if ask == "recoverable":
        return "yes" if is_recoverable(ops) else "no"
    if ask == "cascadeless":
        return "yes" if is_cascadeless(ops) else "no"
    raise ValueError(f"Unknown ask: {ask}")


def grade(spec: dict, student_answer: str) -> bool:
    expected = solve(spec)
    s = student_answer.strip().lower()
    if spec["ask"] == "serial_order" and expected != "not serializable":
        return re.findall(r"\d+", s) == re.findall(r"\d+", expected)
    if expected == "not serializable":
        return "not" in s or s.startswith("n")
    return s[:1] == expected[0]
