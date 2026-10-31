import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from tutor import clock, config, db, item_bank, practice, students
from tutor.graph import get_graph
from tutor.llm import LLM
from tutor.orchestrator import submit_answer
from tutor.retrieval import NotesIndex
from tutor.selector import QueueEntry


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ITEMS_PATH", tmp_path / "items.jsonl")
    conn = db.init_db(tmp_path / "app.db")
    graph = get_graph()
    item_bank.load_all(conn, graph, [config.CONTENT_DIR / "seed_items.yaml"])
    return conn, graph, students.create(conn, "S")


def test_streak_counts_consecutive_days(env):
    conn, graph, sid = env
    today = date(2026, 10, 31)
    item_id = item_bank.items_for(conn, "keys")[0]["id"]
    for d in (0, 1, 2, 4):
        conn.execute("INSERT INTO responses(student_id, item_id, correct, created_at) VALUES (?,?,1,?)",
                     (sid, item_id, (today - timedelta(days=d)).isoformat() + "T10:00:00"))
    assert practice.streak(conn, sid, today) == 3
    assert practice.streak(conn, sid, today + timedelta(days=1)) == 3   # not broken until tomorrow ends
    assert practice.streak(conn, sid, today + timedelta(days=2)) == 0


def test_next_item_reuses_bank_then_repeats_offline(env):
    conn, graph, sid = env
    entry = QueueEntry("sql_aggregates", "weak concept")
    seen = set()
    hows = []
    for _ in range(3):
        item, how = practice.next_item(conn, graph, NotesIndex([]), None, sid, entry, seen)
        submit_answer(conn, graph, sid, item, "x")
        seen.add(item.id)
        hows.append(how)
    assert hows == ["bank"] * 3          # three seed items for this concept, all different
    assert practice.next_item(conn, graph, NotesIndex([]), None, sid, entry, seen) == (None, "")
    # offline, in a new session: falls back to repeating an item
    assert practice.next_item(conn, graph, NotesIndex([]), None, sid, entry, set())[1] == "repeat"


def test_next_item_generates_when_bank_exhausted(env):
    conn, graph, sid = env
    for r in item_bank.items_for(conn, "cap_theorem"):
        submit_answer(conn, graph, sid, item_bank.from_row(r), "A")
    draft = {"stem": "During a partition, a CP system will:", "options": [
        "Stay available and return stale data", "Refuse some requests to stay consistent",
        "Guarantee C, A and P", "Drop partition tolerance"], "answer": "B",
        "misconception_map": {"C": "MC-CAP-01"}, "solution": "CP gives up availability during a partition."}
    replies = [json.dumps(draft), '{"answer": "B", "ambiguous": false}']
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=replies.pop(0)))], usage=None))))
    item, how = practice.next_item(conn, graph, NotesIndex([]), LLM(conn, client=client), sid,
                                   QueueEntry("cap_theorem", "misconception", "MC-CAP-01"), set())
    assert how == "generated" and item.source == "generated" and item.verified
    assert config.ITEMS_PATH.read_text().count("\n") == 1


def test_band_for_targets_seventy_percent(env):
    conn, graph, sid = env
    assert practice.band_for(conn, sid, "bcnf") == "easy"     # new student (Elo 1100) → easy items ~64%
