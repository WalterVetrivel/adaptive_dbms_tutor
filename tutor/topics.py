"""Per-topic status for a student, and the layout of the clickable concept map."""
from __future__ import annotations

import sqlite3
import textwrap
from dataclasses import dataclass

import networkx as nx
import plotly.graph_objects as go

from . import learner_model
from .graph import ConceptGraph
from .viz import mastery_colour

MASTERED, WEAK = 0.7, 0.4
STATUS_LABEL = {"mastered": "✅ Mastered", "learning": "🟨 In progress", "needs_work": "🟥 Needs work",
                "not_started": "⬜ Not started"}


def status(p: float | None, attempted: bool) -> str:
    if not attempted or p is None:
        return "not_started"
    return "mastered" if p >= MASTERED else ("learning" if p >= WEAK else "needs_work")


@dataclass
class TopicState:
    concept_id: str
    mastery: float | None      # None = never touched (not even by propagation)
    attempts: int
    status: str


def states(conn: sqlite3.Connection, graph: ConceptGraph, student_id: str) -> dict[str, TopicState]:
    m = learner_model.get_all(conn, student_id)
    n = learner_model.attempts(conn, student_id)
    return {cid: TopicState(cid, m.get(cid), n.get(cid, 0), status(m.get(cid), bool(n.get(cid))))
            for cid in graph.concepts}


def counts(st: dict[str, TopicState]) -> dict[str, int]:
    out = {k: 0 for k in STATUS_LABEL}
    for s in st.values():
        out[s.status] += 1
    return out


# ---- clickable map -----------------------------------------------------------------
BOX_W, BOX_H, GAP_X, GAP_Y = 1.0, 0.55, 0.28, 0.16


def layout(graph: ConceptGraph, unit: int) -> dict[str, tuple[float, float]]:
    """Layered left-to-right layout of one unit: column = longest prerequisite chain within the unit;
    within a column, nodes are ordered by the mean y of their parents (fewer crossings)."""
    ids = [c.id for c in graph.by_unit(unit)]
    sub = graph.g.subgraph(ids)
    depth: dict[str, int] = {}
    for cid in nx.topological_sort(sub):
        depth[cid] = 1 + max((depth[p] for p in sub.predecessors(cid)), default=-1)
    cols: dict[int, list[str]] = {}
    for cid in ids:
        cols.setdefault(depth[cid], []).append(cid)
    pos: dict[str, tuple[float, float]] = {}
    for d in sorted(cols):
        col = cols[d]
        if d:
            col.sort(key=lambda c: -sum(pos[p][1] for p in sub.predecessors(c)) / max(1, sub.in_degree(c)))
        height = len(col) * BOX_H + (len(col) - 1) * GAP_Y
        for i, cid in enumerate(col):
            pos[cid] = (d * (BOX_W + GAP_X), height / 2 - BOX_H / 2 - i * (BOX_H + GAP_Y))
    return pos


def map_figure(graph: ConceptGraph, unit: int, st_map: dict[str, TopicState],
               highlight: set[str] | None = None) -> go.Figure:
    """One unit of the concept map as a Plotly figure. Each box carries its concept id as customdata, so a
    click (Streamlit on_select) can open the topic page."""
    highlight = highlight or set()
    pos = layout(graph, unit)
    fig = go.Figure()
    ex, ey = [], []
    for a, b in graph.g.edges():
        if a in pos and b in pos:
            (x0, y0), (x1, y1) = pos[a], pos[b]
            ex += [x0 + BOX_W / 2, x1 - BOX_W / 2, None]
            ey += [y0, y1, None]
    fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color="#9ca3af", width=1), hoverinfo="skip"))
    for cid, (x, y) in pos.items():
        c, s = graph.concepts[cid], st_map[cid]
        border = "#2563eb" if cid in highlight else ("#374151" if c.demo_core else "#9ca3af")
        fig.add_shape(type="rect", x0=x - BOX_W / 2, x1=x + BOX_W / 2, y0=y - BOX_H / 2, y1=y + BOX_H / 2,
                      line=dict(color=border, width=3 if cid in highlight else (2 if c.demo_core else 1)),
                      fillcolor=mastery_colour(s.mastery if s.attempts or s.mastery is not None else None),
                      layer="below")
        label = "<br>".join(textwrap.wrap(c.name, 14, break_long_words=False)[:3])
        if s.mastery is not None:
            label += f"<br><b>{s.mastery:.0%}</b>"
        fig.add_annotation(x=x, y=y, text=label, showarrow=False, font=dict(size=10, color="#111827"))
    xs, ys = zip(*pos.values())
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers", customdata=list(pos),
        marker=dict(symbol="square", size=64, color="rgba(0,0,0,0.01)", line=dict(width=0)),
        hovertext=[f"<b>{graph.concepts[c].name}</b><br>{STATUS_LABEL[st_map[c].status]}<br>Click to open"
                   for c in pos], hoverinfo="text"))
    span_x, span_y = max(xs) - min(xs) + BOX_W * 1.2, max(ys) - min(ys) + BOX_H * 1.4
    height = int(min(720, max(240, 1000 * span_y / max(span_x, 4.0))))
    fig.update_layout(showlegend=False, height=height, margin=dict(l=5, r=5, t=5, b=5),
                      xaxis=dict(visible=False, range=[min(xs) - BOX_W * 0.6, max(xs) + BOX_W * 0.6]),
                      yaxis=dict(visible=False, scaleanchor=None,
                                 range=[min(ys) - BOX_H * 0.7, max(ys) + BOX_H * 0.7]),
                      dragmode=False, clickmode="event+select", plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig
