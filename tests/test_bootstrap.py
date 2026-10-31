from tutor import bootstrap, clock, config, db, learner_model
from tutor.graph import get_graph


def test_fresh_install_bootstraps_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAMPLE_DB_PATH", tmp_path / "sample.db")
    conn = db.init_db(tmp_path / "app.db")
    graph = get_graph()
    bootstrap.ensure_all(conn, graph)
    assert (tmp_path / "sample.db").exists()
    assert conn.execute("SELECT COUNT(*) FROM items WHERE verified=1").fetchone()[0] >= 56
    assert conn.execute("SELECT COUNT(*) FROM students WHERE is_simulated=1").fetchone()[0] == 25
    assert bootstrap.ensure_demo_class(conn, graph) is False        # idempotent


def test_reset_demo(tmp_path):
    conn = db.init_db(tmp_path / "app.db")
    graph = get_graph()
    bootstrap.ensure_items(conn, graph)
    bootstrap.ensure_all(conn, graph, demo_class=False)
    learner_model.update(conn, graph, "riya", "bcnf", False, "fd", "hard", clock.now(conn))
    clock.advance(conn, 3)
    bootstrap.reset_demo(conn)
    assert learner_model.get_all(conn, "riya") == {} and clock.offset_days(conn) == 0
