"""Shared data models (Pydantic) for items and agent outputs."""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ItemType = Literal["mcq", "sql", "fd", "schedule"]
Band = Literal["easy", "medium", "hard"]
BAND_ELO = {"easy": 1000.0, "medium": 1200.0, "hard": 1400.0}


class Item(BaseModel):
    id: str = ""
    concept_id: str
    type: ItemType
    difficulty_band: Band
    stem: str
    options: list[str] | None = None          # MCQ: 4 options, answer is "A".."D"
    answer: str                               # MCQ letter / canonical answer / "" for SQL
    reference_sql: str | None = None
    wrong_variants: list[str] = Field(default_factory=list)   # SQL: plausible wrong queries (must differ)
    solution: str = ""
    misconception_map: dict[str, str] = Field(default_factory=dict)   # option letter -> MC id
    target_misconception: str | None = None
    fd_spec: dict | None = None               # FD items: {"attributes": "ABCD", "fds": "A->B, ...", "ask": ...}
    schedule_spec: dict | None = None         # schedule items: {"schedule": "r1(A) w2(A) ...", "ask": ...}
    source: str = "generated"
    verified: bool = False
    verification_note: str = ""

    @property
    def elo(self) -> float:
        return BAND_ELO[self.difficulty_band]

    def ensure_id(self) -> "Item":
        if not self.id:
            h = hashlib.sha1(f"{self.concept_id}|{self.type}|{self.stem}".encode()).hexdigest()[:10]
            self.id = f"{self.concept_id}-{self.type}-{h}"
        return self

    @field_validator("options")
    @classmethod
    def _four_options(cls, v):
        if v is not None and len(v) != 4:
            raise ValueError("MCQ items need exactly 4 options")
        return v


LETTERS = ["A", "B", "C", "D"]
