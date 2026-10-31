import json
from types import SimpleNamespace

import pytest

from tutor import config, db, item_bank, students
from tutor.agents.analyst import make_analyst
from tutor.agents.explainer import explain
from tutor.graph import get_graph
from tutor.llm import LLM
from tutor.orchestrator import submit_answer
from tutor.retrieval import Chunk, NotesIndex


class ScriptedClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.replies.pop(0)))],
                               usage=None)


@pytest.fixture
def env(tmp_path):
    conn = db.init_db(tmp_path / "app.db")
    graph = get_graph()
    item_bank.load_all(conn, graph, [config.CONTENT_DIR / "seed_items.yaml"])
    return conn, graph, students.create(conn, "S")


def _item(conn, concept, typ):
    return next(item_bank.from_row(r) for r in item_bank.items_for(conn, concept) if r["type"] == typ)


def test_analyst_reads_reasoning_and_filters_unknown_ids(env):
    conn, graph, sid = env
    item = _item(conn, "nf_3", "fd")   # A->B, B->C : answer 2NF
    reply = {"matches": [{"id": "MC-NF-02", "confidence": 0.85}, {"id": "MC-MADE-UP", "confidence": 0.9}],
             "error_type": "conceptual", "rationale": "Thinks 2NF is about transitive dependencies",
             "flawed_reasoning": False}
    client = ScriptedClient([json.dumps(reply)])
    analyst = make_analyst(LLM(conn, client=client), graph)
    out = submit_answer(conn, graph, sid, item, "3NF", "there is no transitive dependency so it's 3NF",
                        analyst=analyst)
    assert out.diagnosis.source == "llm"
    assert out.diagnosis.misconceptions == [("MC-NF-02", 0.85)]
    prompt = client.calls[0]["messages"][1]["content"]
    assert "there is no transitive dependency" in prompt and "MC-NF-02" in prompt


def test_analyst_keeps_strong_rule_hits(env):
    conn, graph, sid = env
    item = next(item_bank.from_row(r) for r in item_bank.items_for(conn, "sql_group_by_having", misconception="MC-AGG-01")
                if r["type"] == "sql")
    client = ScriptedClient([json.dumps({"matches": [], "error_type": "syntax", "rationale": "typo"})])
    out = submit_answer(conn, graph, sid, item, "SELECT dept_id FROM employee WHERE COUNT(*) > 5 GROUP BY dept_id",
                        "where filters", analyst=make_analyst(LLM(conn, client=client), graph))
    assert ("MC-AGG-01", 0.95) in out.diagnosis.misconceptions


def test_right_answer_wrong_reason_is_partial(env):
    conn, graph, sid = env
    item = _item(conn, "two_phase_locking", "mcq")
    reply = {"matches": [{"id": "MC-TX-01", "confidence": 0.8}], "error_type": "conceptual",
             "rationale": "believes 2PL avoids deadlock", "flawed_reasoning": True}
    out = submit_answer(conn, graph, sid, item, item.answer, "because 2PL also stops deadlocks",
                        analyst=make_analyst(LLM(conn, client=ScriptedClient([json.dumps(reply)])), graph))
    assert out.grade.correct and out.diagnosis.flawed_reasoning
    assert out.mastery.main.after < 0.5          # blended update, not a full correct update
    assert out.diagnosis.misconceptions[0][0] == "MC-TX-01"


def test_explainer_uses_notes_and_falls_back_offline(env):
    conn, graph, sid = env
    item = _item(conn, "bcnf", "fd")
    out = submit_answer(conn, graph, sid, item, "BCNF", "")
    notes = NotesIndex([Chunk(0, "u2.pdf", 2, 5, "Boyce / Codd Normal Form (BCNF)", "BCNF every determinant superkey"),
                        Chunk(1, "u3.pdf", 3, 1, "Two Phase Locking", "growing shrinking phase locks"),
                        Chunk(2, "u4.pdf", 4, 1, "RAID", "striping mirroring parity disks")])
    fb = explain(None, graph, notes, item, "BCNF", "", out)
    assert fb.source == "fallback" and fb.notes and "3NF" in fb.text
    client = ScriptedClient([json.dumps({"explanation": "C -> B has a non-key determinant.",
                                         "contrast_question": "Is R(A,B) with A->B in BCNF?"})])
    ex = explain(LLM(conn, client=client), graph, notes, item, "BCNF", "", out)
    assert ex.source == "llm" and ex.contrast_question
    assert "BCNF every determinant" in client.calls[0]["messages"][1]["content"]
