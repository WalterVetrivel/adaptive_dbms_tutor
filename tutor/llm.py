"""Groq client wrapper built for the free tier.

- Two model tiers (large / small), configured in .env.
- Every JSON call is cached in SQLite, keyed by (model, messages), so repeats are free.
- HTTP 429: honour Retry-After, back off, then fall back to the other tier.
- Responses are requested in JSON mode and validated with Pydantic by the caller.
- OFFLINE_MODE (or no API key) raises LLMUnavailable so callers use rule-based fallbacks.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from . import config, db

Tier = Literal["large", "small"]
T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    """Raised when no LLM call could be completed (offline, rate-limited, or failing)."""


def _model_for(tier: Tier) -> str:
    return config.MODEL_LARGE if tier == "large" else config.MODEL_SMALL


def _cache_key(model: str, messages: list[dict[str, str]], temperature: float) -> str:
    raw = json.dumps({"m": model, "msgs": messages, "t": temperature}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


class LLM:
    def __init__(self, conn: sqlite3.Connection | None = None, client: Any | None = None):
        self.conn = conn or db.init_db()
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            if config.OFFLINE_MODE:
                raise LLMUnavailable("Offline mode: no GROQ_API_KEY or OFFLINE_MODE=1")
            from groq import Groq

            self._client = Groq(api_key=config.GROQ_API_KEY, max_retries=0, timeout=30)
        return self._client

    # ---- logging / cache -------------------------------------------------
    def _log(self, agent: str, model: str, cached: bool, ok: bool, latency_ms: int = 0,
             usage: Any = None, error: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO llm_calls(agent, model, cached, ok, latency_ms, prompt_tokens, completion_tokens, error)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (agent, model, int(cached), int(ok), latency_ms,
             getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None), error),
        )
        self.conn.commit()

    def _cache_get(self, key: str) -> str | None:
        row = self.conn.execute("SELECT response FROM llm_cache WHERE key=?", (key,)).fetchone()
        return row["response"] if row else None

    def _cache_put(self, key: str, model: str, response: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO llm_cache(key, model, response) VALUES (?,?,?)",
                          (key, model, response))
        self.conn.commit()

    # ---- calls -----------------------------------------------------------
    def _call(self, model: str, messages: list[dict[str, str]], temperature: float, json_mode: bool,
              max_tokens: int) -> tuple[str, Any]:
        kwargs: dict[str, Any] = dict(model=model, messages=messages, temperature=temperature,
                                      max_tokens=max_tokens)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or "", getattr(resp, "usage", None)

    def complete(self, messages: list[dict[str, str]], *, agent: str, tier: Tier = "large",
                 temperature: float = 0.3, json_mode: bool = True, max_tokens: int = 1200,
                 use_cache: bool = True) -> str:
        """Return the raw completion text, trying the requested tier then the other one."""
        tiers: list[Tier] = [tier, "small" if tier == "large" else "large"]
        last_err: Exception | None = None
        for t in tiers:
            model = _model_for(t)
            key = _cache_key(model, messages, temperature)
            if use_cache and (hit := self._cache_get(key)) is not None:
                self._log(agent, model, cached=True, ok=True)
                return hit
            for attempt in range(2):
                start = time.monotonic()
                try:
                    text, usage = self._call(model, messages, temperature, json_mode, max_tokens)
                except LLMUnavailable:
                    raise
                except Exception as e:  # groq.RateLimitError, APIError, network errors
                    last_err = e
                    status = getattr(e, "status_code", None)
                    self._log(agent, model, cached=False, ok=False,
                              latency_ms=int((time.monotonic() - start) * 1000), error=f"{status}: {e}"[:300])
                    if status == 429 and attempt == 0:
                        retry_after = _retry_after(e)
                        if retry_after is not None and retry_after <= 8:
                            time.sleep(retry_after)
                            continue
                    break  # move to the other tier
                self._log(agent, model, cached=False, ok=True,
                          latency_ms=int((time.monotonic() - start) * 1000), usage=usage)
                if use_cache:
                    self._cache_put(key, model, text)
                return text
        raise LLMUnavailable(f"All model tiers failed: {last_err}")

    def json(self, messages: list[dict[str, str]], schema: type[T], *, agent: str, tier: Tier = "large",
             temperature: float = 0.3, max_tokens: int = 1200) -> T:
        """Call in JSON mode and validate against `schema`; retry once with the error shown to the model."""
        text = self.complete(messages, agent=agent, tier=tier, temperature=temperature, max_tokens=max_tokens)
        try:
            return schema.model_validate_json(_strip_fences(text))
        except ValidationError as e:
            retry_msgs = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"That JSON was invalid: {e.errors()[:3]}. Reply with corrected JSON only."},
            ]
            text2 = self.complete(retry_msgs, agent=agent, tier=tier, temperature=0.0, max_tokens=max_tokens)
            try:
                return schema.model_validate_json(_strip_fences(text2))
            except ValidationError as e2:
                raise LLMUnavailable(f"Invalid JSON after retry: {e2}") from e2

    def usage_summary(self) -> dict[str, int]:
        row = self.conn.execute(
            "SELECT COUNT(*) n, SUM(cached) cached, SUM(1-ok) failed, COALESCE(SUM(prompt_tokens),0) pt,"
            " COALESCE(SUM(completion_tokens),0) ct FROM llm_calls").fetchone()
        return {"calls": row["n"] or 0, "cached": row["cached"] or 0, "failed": row["failed"] or 0,
                "prompt_tokens": row["pt"], "completion_tokens": row["ct"]}


def _retry_after(e: Exception) -> float | None:
    resp = getattr(e, "response", None)
    headers = getattr(resp, "headers", None) or {}
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()
