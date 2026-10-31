import random

import pytest

from tutor import (calibration, clock, config, db, item_bank, learner_model, misconception_tracker, rules,
                   scheduler, selector, students)
from tutor.graph import get_graph
from tutor.orchestrator import submit_answer


@pytest.fixture
def env(tmp_path):
    conn = db.init_db(tmp_path / "app.db")
    graph = get_graph()
    item_bank.load_all(conn, graph, [config.CONTENT_DIR / "seed_items.yaml"])
    sid = students.create(conn, "Test Student")
    return conn, graph, sid


def sql_item(conn, concept, mc=None):
    rows = item_bank.items_for(conn, concept, misconception=mc)
    return next(item_bank.from_row(r) for r in rows if r["type"] == "sql")


# ---- BKT ---------------------------------------------------------------------

def test_bkt_direction_and_difficulty():
    g, s = learner_model.params("sql", "medium")
    assert learner_model.bkt_update(0.3, True, g, s) > 0.3
    assert learner_model.bkt_update(0.6, False, g, s) < 0.6
    # correct on a hard item is stronger evidence than on an easy one
    hard = learner_model.bkt_update(0.3, True, *learner_model.params("mcq", "hard"))
    easy = learner_model.bkt_update(0.3, True, *learner_model.params("mcq", "easy"))
    assert hard > easy
    # right-for-the-wrong-reason sits between correct and wrong
    partial = learner_model.bkt_update(0.5, True, g, s, partial=True)
    assert learner_model.bkt_update(0.5, False, g, s) < partial < learner_model.bkt_update(0.5, True, g, s)


def test_wrong_answer_propagates_to_prerequisites(env):
    conn, graph, sid = env
    now = clock.now(conn)
    upd = learner_model.update(conn, graph, sid, "sql_group_by_having", False, "sql", "medium", now)
    assert upd.main.after < upd.main.before
    assert {c.concept_id for c in upd.propagated} == {"sql_aggregates"}
    assert learner_model.get_p(conn, sid, "sql_aggregates") < learner_model.P_INIT
    # propagated concepts are not counted as attempted
    assert "sql_aggregates" not in learner_model.get_all(conn, sid, attempted_only=True)
    assert learner_model.events(conn, sid, "sql_aggregates")[0]["cause"].startswith("prerequisite of")


# ---- Elo / FSRS --------------------------------------------------------------

def test_elo_moves_both_ratings(env):
    conn, graph, sid = env
    item = sql_item(conn, "sql_aggregates")
    learner_model.update(conn, graph, sid, item.concept_id, True, "sql", "easy", clock.now(conn))
    s0, i0 = calibration.student_elo(conn, sid, item.concept_id), item_bank.get(conn, item.id).elo
    s1, i1 = calibration.update(conn, sid, item.concept_id, item.id, True)
    assert s1 > s0 and i1 < i0
    assert abs(calibration.expected(1200, 1200) - 0.5) < 1e-9


def test_fsrs_reviews_become_due_after_clock_advances(env):
    conn, graph, sid = env
    now = clock.now(conn)
    scheduler.review(conn, sid, "bcnf", scheduler.rating_for(True), now)
    assert scheduler.due(conn, sid, now) == []
    later = clock.advance(conn, 5)
    assert scheduler.due(conn, sid, later) == ["bcnf"]
    assert 0 < scheduler.retrievability(conn, sid, "bcnf", later) < 1
    clock.reset(conn)


# ---- misconceptions ------------------------------------------------------------

def test_misconception_lifecycle(env):
    conn, graph, sid = env
    now = clock.now(conn)
    assert misconception_tracker.record_evidence(conn, sid, "MC-AGG-01", 0.5, None, now) == "suspected"
    assert misconception_tracker.record_evidence(conn, sid, "MC-AGG-01", 0.5, None, now) == "active"
    assert misconception_tracker.record_correct(conn, sid, ["MC-AGG-01"], now) == []
    assert misconception_tracker.record_correct(conn, sid, ["MC-AGG-01"], now) == ["MC-AGG-01"]


def test_sql_rules():
    hits = dict(rules.from_sql("SELECT dept_id FROM employee WHERE COUNT(*) > 5 GROUP BY dept_id",
                               "SELECT dept_id FROM employee GROUP BY dept_id HAVING COUNT(*) > 5"))
    assert "MC-AGG-01" in hits
    assert "MC-NULL-01" in dict(rules.from_sql("select name from employee where commission = null"))
    ref = "SELECT d.dept_name, e.name FROM department d LEFT JOIN employee e ON e.dept_id = d.dept_id AND e.salary > 100000"
    stu = "SELECT d.dept_name, e.name FROM department d LEFT JOIN employee e ON e.dept_id = d.dept_id WHERE e.salary > 100000"
    assert "MC-JOIN-01" in dict(rules.from_sql(stu, ref))


# ---- selection -----------------------------------------------------------------

def test_diagnostic_goes_to_prerequisite_after_wrong_answer(env):
    conn, graph, sid = env
    first = selector.next_diagnostic_concept(graph, conn, sid, [], None)
    assert first in graph.core_ids()
    nxt = selector.next_diagnostic_concept(graph, conn, sid, ["sql_group_by_having"], "sql_group_by_having")
    assert nxt == "sql_aggregates"


def test_diagnostic_spreads_across_units(env):
    conn, graph, sid = env
    asked = []
    for _ in range(5):
        asked.append(selector.next_diagnostic_concept(graph, conn, sid, asked, None))
    assert len({graph.concepts[c].unit for c in asked}) == 5


def test_pick_item_prefers_target_misconception_and_unseen(env):
    conn, graph, sid = env
    item = selector.pick_item(conn, sid, "sql_joins", misconception="MC-JOIN-01", rng=random.Random(0))
    assert item.target_misconception == "MC-JOIN-01"
    other = selector.pick_item(conn, sid, "sql_joins", exclude={item.id}, rng=random.Random(0))
    assert other and other.id != item.id


def test_practice_queue_mixes_sources(env):
    conn, graph, sid = env
    now = clock.now(conn)
    misconception_tracker.record_evidence(conn, sid, "MC-NULL-03", 0.9, None, now)
    learner_model.update(conn, graph, sid, "bcnf", False, "fd", "hard", now)
    scheduler.review(conn, sid, "keys", scheduler.rating_for(True), now - __import__("datetime").timedelta(days=30))
    q = selector.practice_queue(conn, graph, sid, now, size=8)
    reasons = {e.reason for e in q}
    assert {"misconception", "review due", "weak concept", "new"} <= reasons
    assert next(e for e in q if e.reason == "misconception").concept_id == "sql_subqueries"
    assert len(q) == 8 and len({e.concept_id for e in q}) == 8


# ---- orchestrator end to end -----------------------------------------------------

def test_submit_wrong_sql_answer_full_pipeline(env):
    conn, graph, sid = env
    item = sql_item(conn, "sql_group_by_having", "MC-AGG-01")
    out = submit_answer(conn, graph, sid, item, "SELECT dept_id FROM employee WHERE COUNT(*) > 5 GROUP BY dept_id",
                        reasoning="WHERE filters the rows I want", mode="diagnostic")
    assert not out.grade.correct and "aggregate" in out.grade.sql_error
    assert ("MC-AGG-01", 0.95) in out.diagnosis.misconceptions
    assert out.newly_active == ["MC-AGG-01"]
    assert out.mastery.main.after < out.mastery.main.before
    assert conn.execute("SELECT COUNT(*) FROM diagnoses").fetchone()[0] == 1
    assert scheduler.due(conn, sid, clock.now(conn)) == []          # 'Again' is due tomorrow, not now
    # two correct answers on items targeting it resolve the misconception
    for _ in range(2):
        out2 = submit_answer(conn, graph, sid, item, item.reference_sql)
    assert out2.grade.correct and out2.resolved == ["MC-AGG-01"]


def test_analyst_failure_falls_back_to_rules(env):
    conn, graph, sid = env
    item = sql_item(conn, "sql_basic_structure", "MC-NULL-01")
    errors = []

    def broken(*a, **k):
        raise RuntimeError("rate limited")

    out = submit_answer(conn, graph, sid, item, "SELECT name FROM employee WHERE commission = NULL",
                        reasoning="x", analyst=broken, on_error=errors.append)
    assert errors and out.diagnosis.source == "rule"
    assert out.diagnosis.misconceptions[0][0] == "MC-NULL-01"
