from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from tutor import db
from tutor.llm import LLM, LLMUnavailable


class Out(BaseModel):
    answer: str


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=r))],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


class RateLimited(Exception):
    status_code = 429


@pytest.fixture
def conn(tmp_path):
    return db.init_db(tmp_path / "app.db")


def test_json_call_is_cached(conn):
    fake = FakeClient(['{"answer": "HAVING"}'])
    llm = LLM(conn, client=fake)
    msgs = [{"role": "user", "content": "q"}]
    assert llm.json(msgs, Out, agent="t").answer == "HAVING"
    assert llm.json(msgs, Out, agent="t").answer == "HAVING"   # served from cache
    assert len(fake.calls) == 1
    assert fake.calls[0]["response_format"] == {"type": "json_object"}
    assert llm.usage_summary()["cached"] == 1


def test_invalid_json_is_retried(conn):
    fake = FakeClient(['{"nope": 1}', '```json\n{"answer": "ok"}\n```'])
    assert LLM(conn, client=fake).json([{"role": "user", "content": "x"}], Out, agent="t").answer == "ok"


def test_rate_limit_falls_back_to_other_tier(conn):
    fake = FakeClient([RateLimited("slow down"), '{"answer": "from small"}'])
    out = LLM(conn, client=fake).json([{"role": "user", "content": "y"}], Out, agent="t", tier="large")
    assert out.answer == "from small"
    assert fake.calls[0]["model"] != fake.calls[1]["model"]


def test_all_tiers_failing_raises(conn):
    fake = FakeClient([RuntimeError("down"), RuntimeError("down")])
    with pytest.raises(LLMUnavailable):
        LLM(conn, client=fake).complete([{"role": "user", "content": "z"}], agent="t")
