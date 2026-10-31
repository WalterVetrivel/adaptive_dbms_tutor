"""Concept graph and misconception library, loaded from content/*.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import networkx as nx
import yaml

from . import config


@dataclass(frozen=True)
class Concept:
    id: str
    name: str
    unit: int
    bloom: str
    prereqs: tuple[str, ...]
    item_types: tuple[str, ...]
    demo_core: bool
    description: str
    misconceptions: tuple[str, ...]
    notes_file: str
    notes_section: str


@dataclass(frozen=True)
class Misconception:
    id: str
    belief: str
    concepts: tuple[str, ...]
    remediation: str


@dataclass
class ConceptGraph:
    units: dict[int, str]
    concepts: dict[str, Concept]
    misconceptions: dict[str, Misconception]
    g: nx.DiGraph = field(repr=False)

    # ---- queries -----------------------------------------------------------
    def prereqs(self, cid: str) -> list[str]:
        return list(self.g.predecessors(cid))

    def dependants(self, cid: str) -> list[str]:
        return list(self.g.successors(cid))

    def ancestors(self, cid: str) -> set[str]:
        return nx.ancestors(self.g, cid)

    def core_ids(self) -> list[str]:
        return [c.id for c in self.concepts.values() if c.demo_core]

    def by_unit(self, unit: int) -> list[Concept]:
        return [c for c in self.concepts.values() if c.unit == unit]

    def topo_order(self) -> list[str]:
        return list(nx.topological_sort(self.g))

    def misconceptions_for(self, cid: str) -> list[Misconception]:
        return [self.misconceptions[m] for m in self.concepts[cid].misconceptions]


def load_graph(graph_path: Path | None = None, mc_path: Path | None = None) -> ConceptGraph:
    graph_path = graph_path or config.CONCEPT_GRAPH_PATH
    mc_path = mc_path or config.MISCONCEPTIONS_PATH
    raw = yaml.safe_load(graph_path.read_text(encoding="utf-8"))
    mraw = yaml.safe_load(mc_path.read_text(encoding="utf-8"))

    units = {u["id"]: u["title"] for u in raw["units"]}
    concepts: dict[str, Concept] = {}
    for c in raw["concepts"]:
        if c["id"] in concepts:
            raise ValueError(f"Duplicate concept id: {c['id']}")
        concepts[c["id"]] = Concept(
            id=c["id"], name=c["name"], unit=int(c["unit"]), bloom=c["bloom"],
            prereqs=tuple(c.get("prereqs") or []), item_types=tuple(c.get("item_types") or ["mcq"]),
            demo_core=bool(c.get("demo_core")), description=c.get("description", ""),
            misconceptions=tuple(c.get("misconceptions") or []),
            notes_file=(c.get("notes_ref") or {}).get("file", ""),
            notes_section=(c.get("notes_ref") or {}).get("section", ""),
        )
    misconceptions = {
        m["id"]: Misconception(id=m["id"], belief=m["belief"], concepts=tuple(m["concepts"]),
                               remediation=m["remediation"])
        for m in mraw["misconceptions"]
    }

    g = nx.DiGraph()
    g.add_nodes_from(concepts)
    for c in concepts.values():
        if c.unit not in units:
            raise ValueError(f"{c.id}: unknown unit {c.unit}")
        for p in c.prereqs:
            if p not in concepts:
                raise ValueError(f"{c.id}: unknown prerequisite {p}")
            g.add_edge(p, c.id)
        for m in c.misconceptions:
            if m not in misconceptions:
                raise ValueError(f"{c.id}: unknown misconception {m}")
    if not nx.is_directed_acyclic_graph(g):
        raise ValueError(f"Concept graph has a cycle: {nx.find_cycle(g)}")
    for m in misconceptions.values():
        for cid in m.concepts:
            if cid not in concepts:
                raise ValueError(f"{m.id}: unknown concept {cid}")
    return ConceptGraph(units=units, concepts=concepts, misconceptions=misconceptions, g=g)


@lru_cache(maxsize=1)
def get_graph() -> ConceptGraph:
    return load_graph()
