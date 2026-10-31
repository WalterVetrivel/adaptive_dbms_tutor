import json
from types import SimpleNamespace

import pytest

from tutor import config, db, item_bank
from tutor.agents.generator import generate_item
from tutor.graph import get_graph
from tutor.llm import LLM
from tutor.retrieval import NotesIndex
from tutor.schemas import Item
from tutor.verifier import verify


@pytest.fixture
def conn(tmp_path):
    return db.init_db(tmp_path / "app.db")


def test_all_seed_items_verify_and_cover_demo_core(conn):
    graph = get_graph()
    loaded, failures = item_bank.load_all(conn, graph, [config.CONTENT_DIR / "seed_items.yaml"])
    assert failures == []
    assert loaded >= 50
    assert set(graph.core_ids()) <= set(item_bank.counts(conn))
    row = item_bank.items_for(conn, "sql_group_by_having", misconception="MC-AGG-01")[0]
    item = item_bank.from_row(row)
    assert item.reference_sql and item.wrong_variants


def test_verifier_rejects_bad_items():
    graph = get_graph()
    wrong_fd = Item(concept_id="nf_3", type="fd", difficulty_band="easy", stem="?", answer="BCNF",
                    fd_spec={"attributes": "ABC", "fds": "A->B, B->C", "ask": "normal_form"})
    assert not verify(wrong_fd, graph)[0]
    non_discriminating = Item(concept_id="sql_aggregates", type="sql", difficulty_band="easy", stem="?", answer="",
                              reference_sql="SELECT COUNT(*) FROM employee",
                              wrong_variants=["SELECT COUNT(emp_id) FROM employee"])
    assert not verify(non_discriminating, graph)[0]
    tagged_correct = Item(concept_id="keys", type="mcq", difficulty_band="easy", stem="?", answer="A",
                          options=["a", "b", "c", "d"], misconception_map={"A": "MC-KEY-01"})
    assert not verify(tagged_correct, graph)[0]


class ScriptedClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.replies.pop(0)))],
                               usage=None)


def test_generator_regenerates_after_failed_verification(conn):
    graph = get_graph()
    bad = {"stem": "Count employees with commission", "reference_sql": "SELECT COUNT(*) FROM employee",
           "wrong_variants": ["SELECT COUNT(emp_id) FROM employee"], "solution": "x"}
    good = {"stem": "How many employees have a commission?", "reference_sql": "SELECT COUNT(commission) FROM employee",
            "wrong_variants": ["SELECT COUNT(*) FROM employee"], "solution": "COUNT(col) skips NULLs"}
    llm = LLM(conn, client=ScriptedClient([json.dumps(bad), json.dumps(good)]))
    item, log = generate_item(llm, graph, NotesIndex([]), "sql_aggregates", "sql", "easy", "MC-NULL-02")
    assert item and item.verified and len(log) == 1 and "same result" in log[0]


def test_generator_mcq_needs_cross_check_agreement(conn):
    graph = get_graph()
    draft = {"stem": "2PL guarantees?", "options": ["Deadlock freedom", "Conflict serializability",
                                                    "No waiting", "No locks"],
             "answer": "B", "misconception_map": {"A": "MC-TX-01"}, "solution": "..."}
    llm = LLM(conn, client=ScriptedClient([json.dumps(draft), '{"answer": "A", "ambiguous": false}',
                                           json.dumps({**draft, "stem": "Basic 2PL guarantees?"}),
                                           '{"answer": "B", "ambiguous": false}']))
    item, log = generate_item(llm, graph, NotesIndex([]), "two_phase_locking", "mcq", "easy")
    assert item and "cross-check agrees" in item.verification_note
    assert "cross-check answered A" in log[0]
