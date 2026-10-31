import pytest

from tutor import analytics, config, db, item_bank
from tutor.agents.insights import brief, facts
from tutor.graph import get_graph
from tutor.simulation import CLASS, simulate_class


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    conn = db.init_db(tmp_path_factory.mktemp("t") / "app.db")
    graph = get_graph()
    item_bank.load_all(conn, graph, [config.CONTENT_DIR / "seed_items.yaml"])
    counts = simulate_class(conn, graph, days=6, seed=3)
    return conn, graph, list(counts)


def test_simulation_is_realistic(sim):
    conn, graph, ids = sim
    assert len(ids) == len(CLASS)
    stats = {s.misconception_id: s for s in analytics.misconception_stats(conn, ids)}
    # where-having personas surface the WHERE-vs-HAVING misconception
    assert len(stats["MC-AGG-01"].active) >= 4
    # all-rounders have higher mastery than strugglers
    means = dict((s, m) for s, m, _ in analytics.students_at_risk(conn, ids, limit=len(ids)))
    assert means["sim-aarav-s"] > means["sim-irfan-a"]


def test_dashboard_aggregates(sim):
    conn, graph, ids = sim
    m = analytics.mastery_matrix(conn, ids, graph.core_ids())
    assert len(m) == len(ids) and len(m[0]) == len(graph.core_ids())
    gaps = analytics.concept_gaps(conn, graph, ids)
    assert gaps == sorted(gaps, key=lambda g: g.mean)
    assert set(analytics.unit_means(conn, graph, ids)) == {1, 2, 3, 4, 5}
    rr = analytics.recent_responses(conn, ids[1], 5)
    assert rr and "stem" in rr[0].keys()


def test_brief_fallback_offline(sim):
    conn, graph, ids = sim
    b = brief(conn, graph, None, ids)
    assert b.source == "fallback" and b.gaps and b.students_to_watch
    f = facts(conn, graph, ids)
    assert f["class_size"] == len(ids) and f["top_misconceptions"]
