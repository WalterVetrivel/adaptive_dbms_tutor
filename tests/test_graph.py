import pytest
import yaml

from tutor.graph import load_graph


def test_graph_loads_and_is_consistent():
    g = load_graph()
    assert len(g.concepts) == 63
    assert len(g.units) == 5
    assert len(g.core_ids()) == 24
    # every demo-core concept has at least one misconception to diagnose
    assert all(g.concepts[c].misconceptions for c in g.core_ids())
    # prerequisites come before dependants
    order = {c: i for i, c in enumerate(g.topo_order())}
    for a, b in g.g.edges():
        assert order[a] < order[b]
    assert "sql_aggregates" in g.prereqs("sql_group_by_having")
    assert any(m.id == "MC-AGG-01" for m in g.misconceptions_for("sql_group_by_having"))


def test_cycle_is_rejected(tmp_path):
    from tutor import config
    raw = yaml.safe_load(config.CONCEPT_GRAPH_PATH.read_text(encoding="utf-8"))
    for c in raw["concepts"]:
        if c["id"] == "keys":
            c["prereqs"] = ["integrity_constraints"]   # integrity_constraints already depends on keys
    p = tmp_path / "g.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="cycle"):
        load_graph(p, config.MISCONCEPTIONS_PATH)
