"""SQLite storage for app data (students, items, responses, learner model, LLM cache)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    persona TEXT,
    is_simulated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('mcq','sql','fd','schedule')),
    difficulty_band TEXT NOT NULL CHECK (difficulty_band IN ('easy','medium','hard')),
    stem TEXT NOT NULL,
    options_json TEXT,              -- MCQ options as JSON list
    answer TEXT NOT NULL,           -- MCQ letter / canonical answer
    reference_sql TEXT,             -- SQL items
    solution TEXT,                  -- worked explanation
    misconception_map_json TEXT,    -- {"B": "MC-AGG-01", ...}
    target_misconception TEXT,
    elo REAL NOT NULL DEFAULT 1200,
    n_responses INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'generated',
    verified INTEGER NOT NULL DEFAULT 0,
    verification_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_items_concept ON items(concept_id, difficulty_band);

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL REFERENCES students(id),
    item_id TEXT NOT NULL REFERENCES items(id),
    mode TEXT NOT NULL DEFAULT 'practice',   -- diagnostic / practice
    answer TEXT,
    reasoning TEXT,
    correct INTEGER NOT NULL,
    sql_error TEXT,
    time_ms INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_responses_student ON responses(student_id, created_at);

CREATE TABLE IF NOT EXISTS diagnoses (
    response_id INTEGER NOT NULL REFERENCES responses(id),
    misconception_id TEXT,
    confidence REAL,
    error_type TEXT,
    rationale TEXT,
    source TEXT NOT NULL DEFAULT 'llm'       -- llm / rule
);

CREATE TABLE IF NOT EXISTS mastery (
    student_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    p_mastery REAL NOT NULL,
    elo REAL NOT NULL DEFAULT 1200,
    n_attempts INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (student_id, concept_id)
);

CREATE TABLE IF NOT EXISTS mastery_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    before REAL NOT NULL,
    after REAL NOT NULL,
    cause TEXT NOT NULL,
    response_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_cards (
    student_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    card_json TEXT NOT NULL,                 -- serialized FSRS card
    due_at TEXT NOT NULL,
    last_grade TEXT,
    PRIMARY KEY (student_id, concept_id)
);

CREATE TABLE IF NOT EXISTS student_misconceptions (
    student_id TEXT NOT NULL,
    misconception_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('suspected','active','resolved')),
    confidence REAL NOT NULL,
    occurrences INTEGER NOT NULL DEFAULT 1,
    correct_since INTEGER NOT NULL DEFAULT 0,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (student_id, misconception_id)
);

CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    model TEXT NOT NULL,
    cached INTEGER NOT NULL,
    ok INTEGER NOT NULL,
    latency_ms INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS onboarding (
    student_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('completed','skipped')),
    unit_scores_json TEXT NOT NULL DEFAULT '{}',   -- {"1": [correct, asked], ...}
    completed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS study_plan (
    student_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    concept_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (student_id, concept_id)
);

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path or config.APP_DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path: Path | str | None = None) -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
