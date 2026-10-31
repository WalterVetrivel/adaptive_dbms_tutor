import pytest

from tutor import config, db, item_bank, learner_model, onboarding, selector, clock, students
from tutor.graph import get_graph
from tutor.orchestrator import submit_answer


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ITEMS_PATH", tmp_path / "items.jsonl")
    conn = db.init_db(tmp_path / "app.db")
    graph = get_graph()
    item_bank.load_all(conn, graph, [config.CONTENT_DIR / "seed_items.yaml"])
    return conn, graph, students.create(conn, "New Student")


def test_two_questions_per_unit_on_different_concepts(env):
    conn, graph, sid = env
    items = onboarding.choose_items(conn, graph, sid)
    assert len(items) == 2 * len(graph.units)
    for u in graph.units:
        concepts = [i.concept_id for i in items if graph.concepts[i.concept_id].unit == u]
        assert len(concepts) == 2 and len(set(concepts)) == 2
    assert onboarding.choose_items(conn, graph, sid) == items          # deterministic per student/attempt


def test_learning_order_respects_prerequisites(env):
    _, graph, _ = env
    pos = {c: i for i, c in enumerate(onboarding.learning_order(graph))}
    assert all(pos[a] < pos[b] for a, b in graph.g.edges())


def test_first_login_flow_builds_ordered_plan(env):
    conn, graph, sid = env
    assert onboarding.needs_onboarding(conn, sid)
    items = onboarding.choose_items(conn, graph, sid)
    results = []
    for i, item in enumerate(items):
        unit = graph.concepts[item.concept_id].unit
        if unit in (1, 2):                      # weak in units 1-2, strong elsewhere
            onboarding.record_dont_know(conn, graph, sid, item)
            results.append((item.concept_id, False))
        else:
            results.append((item.concept_id, True))
    plan = onboarding.complete(conn, graph, sid, results)
    assert not onboarding.needs_onboarding(conn, sid)
    assert onboarding.unit_scores(conn, sid)[1] == (0, 2) and onboarding.unit_scores(conn, sid)[3] == (2, 2)
    ids = [c for c, _ in plan]
    assert 0 < len(ids) <= onboarding.PLAN_SIZE
    assert all(graph.concepts[c].unit in (1, 2) for c in ids)
    wrong = {c for c, ok in results if not ok}
    assert wrong <= set(ids)
    pos = {c: i for i, c in enumerate(ids)}
    assert all(pos[a] < pos[b] for a, b in graph.g.edges() if a in pos and b in pos)
    steps = onboarding.plan(conn, sid)
    assert [s.concept_id for s in steps] == ids and not any(s.done for s in steps)
    q = selector.practice_queue(conn, graph, sid, clock.now(conn), size=10)
    assert any(e.reason == "study plan" for e in q)


def test_plan_steps_tick_off_with_mastery(env):
    conn, graph, sid = env
    onboarding.complete(conn, graph, sid, [("keys", False)])
    step = next(s for s in onboarding.plan(conn, sid) if s.concept_id == "keys")
    assert not step.done
    now = clock.now(conn)
    for _ in range(4):
        learner_model.update(conn, graph, sid, "keys", True, "mcq", "medium", now)
    assert next(s for s in onboarding.plan(conn, sid) if s.concept_id == "keys").done
    assert "keys" not in onboarding.open_steps(conn, sid)


def test_all_correct_gives_stretch_plan_and_skip(env):
    conn, graph, sid = env
    items = onboarding.choose_items(conn, graph, sid)
    plan = onboarding.complete(conn, graph, sid, [(i.concept_id, True) for i in items])
    assert plan and all("stretch" in r for _, r in plan)
    other = students.create(conn, "Skipper")
    onboarding.skip(conn, other)
    assert onboarding.status(conn, other) == "skipped" and onboarding.plan(conn, other) == []


def test_reset_progress_clears_onboarding(env):
    conn, graph, sid = env
    onboarding.complete(conn, graph, sid, [("keys", False)])
    students.reset_progress(conn, sid)
    assert onboarding.needs_onboarding(conn, sid) and onboarding.plan(conn, sid) == []
