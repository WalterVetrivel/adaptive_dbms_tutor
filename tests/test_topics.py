from tutor import clock, config, db, item_bank, learner_model, students, topics
from tutor.agents.overview import overview
from tutor.graph import get_graph
from tutor.retrieval import NotesIndex


def test_status_buckets():
    assert topics.status(None, False) == "not_started"
    assert topics.status(0.9, False) == "not_started"       # propagation alone doesn't count as practice
    assert topics.status(0.2, True) == "needs_work"
    assert topics.status(0.5, True) == "learning"
    assert topics.status(0.8, True) == "mastered"


def test_states_and_counts(tmp_path):
    conn = db.init_db(tmp_path / "app.db")
    graph = get_graph()
    sid = students.create(conn, "T")
    now = clock.now(conn)
    for _ in range(4):
        learner_model.update(conn, graph, sid, "keys", True, "mcq", "medium", now)
    st = topics.states(conn, graph, sid)
    assert st["keys"].status == "mastered" and st["keys"].attempts == 4
    n = topics.counts(st)
    assert n["mastered"] == 1 and sum(n.values()) == len(graph.concepts)


def test_layout_keeps_prereqs_left_and_boxes_apart():
    graph = get_graph()
    for unit in graph.units:
        pos = topics.layout(graph, unit)
        assert set(pos) == {c.id for c in graph.by_unit(unit)}
        for a, b in graph.g.edges():
            if a in pos and b in pos:
                assert pos[a][0] < pos[b][0]
        assert len(set(pos.values())) == len(pos)


def test_map_figure_carries_concept_ids(tmp_path):
    conn = db.init_db(tmp_path / "app.db")
    graph = get_graph()
    sid = students.create(conn, "T")
    fig = topics.map_figure(graph, 2, topics.states(conn, graph, sid), highlight={"bcnf"})
    clickable = fig.data[-1]
    assert set(clickable.customdata) == {c.id for c in graph.by_unit(2)}


def test_overview_offline_fallback():
    graph = get_graph()
    ov = overview(None, graph, NotesIndex([]), "sql_aggregates")
    assert ov.source == "fallback" and ov.text == graph.concepts["sql_aggregates"].description


def test_overview_with_llm(tmp_path):
    import json
    from types import SimpleNamespace

    from tutor.llm import LLM

    conn = db.init_db(tmp_path / "app.db")
    reply = json.dumps({"overview": "Aggregates summarise rows.", "key_points": ["COUNT(col) skips NULLs"],
                        "example": "SELECT COUNT(*) FROM emp;"})
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=reply))], usage=None))))
    ov = overview(LLM(conn, client=client), get_graph(), NotesIndex([]), "sql_aggregates")
    assert ov.source == "llm" and ov.key_points == ["COUNT(col) skips NULLs"] and "COUNT" in ov.example
