"""Graphviz rendering of the concept graph, coloured by mastery."""
from __future__ import annotations

from .graph import ConceptGraph


def mastery_colour(p: float | None) -> str:
    if p is None:
        return "#e5e7eb"          # not yet assessed
    if p < 0.4:
        return "#fca5a5"          # red
    if p < 0.7:
        return "#fcd34d"          # amber
    return "#86efac"              # green


def to_dot(graph: ConceptGraph, mastery: dict[str, float] | None = None, units: list[int] | None = None,
           core_only: bool = False, highlight: set[str] | None = None, rankdir: str = "LR") -> str:
    mastery = mastery or {}
    highlight = highlight or set()
    keep = {c.id for c in graph.concepts.values()
            if (units is None or c.unit in units) and (not core_only or c.demo_core)}
    lines = ["digraph G {", f"  rankdir={rankdir}; nodesep=0.25; ranksep=0.4;",
             '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10];',
             '  edge [color="#9ca3af", arrowsize=0.6];']
    for u, title in graph.units.items():
        members = [c for c in graph.by_unit(u) if c.id in keep]
        if not members:
            continue
        lines.append(f'  subgraph cluster_{u} {{ label="Unit {u}: {title}"; fontname="Helvetica"; '
                     f'fontsize=11; style="rounded"; color="#d1d5db";')
        for c in members:
            p = mastery.get(c.id)
            label = c.name if p is None else f"{c.name}\\n{p:.0%}"
            pen = "3" if c.id in highlight else ("2" if c.demo_core else "1")
            colour = ', color="#2563eb"' if c.id in highlight else ""
            lines.append(f'    "{c.id}" [label="{label}", fillcolor="{mastery_colour(p)}", penwidth={pen}{colour}];')
        lines.append("  }")
    for a, b in graph.g.edges():
        if a in keep and b in keep:
            lines.append(f'  "{a}" -> "{b}";')
    lines.append("}")
    return "\n".join(lines)
