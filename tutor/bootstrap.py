"""First-run setup, so the app works from a fresh clone (or on Streamlit Community Cloud) with no manual steps."""
from __future__ import annotations

import sqlite3

from . import config, item_bank, students
from .graph import ConceptGraph

DEMO_STUDENT = ("Riya", "riya")


def ensure_sample_db() -> None:
    if not config.SAMPLE_DB_PATH.exists():
        import importlib.util

        spec = importlib.util.spec_from_file_location("build_sample_db", config.ROOT / "scripts" / "build_sample_db.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.build(config.SAMPLE_DB_PATH)


def ensure_items(conn: sqlite3.Connection, graph: ConceptGraph) -> None:
    if not item_bank.counts(conn):
        item_bank.load_all(conn, graph, [p for p in (config.CONTENT_DIR / "seed_items.yaml", config.ITEMS_PATH)
                                         if p.exists()])


def ensure_demo_class(conn: sqlite3.Connection, graph: ConceptGraph) -> bool:
    """Simulate the demo class once if there are no simulated students yet (~3 s, no LLM calls)."""
    if conn.execute("SELECT 1 FROM students WHERE is_simulated=1 LIMIT 1").fetchone():
        return False
    from .simulation import simulate_class

    simulate_class(conn, graph)
    return True


def ensure_all(conn: sqlite3.Connection, graph: ConceptGraph, demo_class: bool = True) -> None:
    ensure_sample_db()
    ensure_items(conn, graph)
    students.create(conn, DEMO_STUDENT[0], student_id=DEMO_STUDENT[1])
    if demo_class:
        ensure_demo_class(conn, graph)


def reset_demo(conn: sqlite3.Connection) -> None:
    """Fresh demo: clear the demo student's progress and the demo clock (class data is kept)."""
    from . import clock

    students.reset_progress(conn, DEMO_STUDENT[1])
    clock.reset(conn)
