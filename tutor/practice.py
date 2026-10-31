"""Practice session logic: turn the queue into concrete items, generating new ones when the bank runs dry."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

from . import calibration, config, item_bank, selector
from .graph import ConceptGraph
from .llm import LLM
from .retrieval import NotesIndex
from .schemas import Item
from .selector import QueueEntry


def streak(conn: sqlite3.Connection, student_id: str, today: date) -> int:
    days = {date.fromisoformat(r["d"]) for r in conn.execute(
        "SELECT DISTINCT substr(created_at, 1, 10) d FROM responses WHERE student_id=?", (student_id,))}
    n, d = 0, today
    if d not in days:
        d -= timedelta(days=1)          # streak survives until the end of today
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n


def answered_today(conn: sqlite3.Connection, student_id: str, now: datetime) -> int:
    return conn.execute("SELECT COUNT(*) FROM responses WHERE student_id=? AND substr(created_at,1,10)=?",
                        (student_id, now.date().isoformat())).fetchone()[0]


def unseen_count(conn: sqlite3.Connection, student_id: str, concept_id: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM items i WHERE concept_id=? AND verified=1 AND NOT EXISTS "
                        "(SELECT 1 FROM responses r WHERE r.item_id=i.id AND r.student_id=?)",
                        (concept_id, student_id)).fetchone()[0]


def band_for(conn: sqlite3.Connection, student_id: str, concept_id: str) -> str:
    """Difficulty band whose Elo gives ~70% predicted success for this student."""
    s = calibration.student_elo(conn, student_id, concept_id)
    from .schemas import BAND_ELO
    return min(BAND_ELO, key=lambda b: abs(calibration.expected(s, BAND_ELO[b]) - selector.TARGET_SUCCESS))


def generate_for(conn: sqlite3.Connection, graph: ConceptGraph, notes: NotesIndex, llm: LLM, student_id: str,
                 entry: QueueEntry) -> tuple[Item | None, list[str]]:
    from .agents.generator import generate_item

    c = graph.concepts[entry.concept_id]
    n = len(item_bank.items_for(conn, c.id, verified_only=False))
    item_type = c.item_types[n % len(c.item_types)]
    mc = entry.misconception or (c.misconceptions[n % len(c.misconceptions)] if c.misconceptions else None)
    item, log = generate_item(llm, graph, notes, c.id, item_type, band_for(conn, student_id, c.id), mc,
                              avoid=[r["stem"] for r in item_bank.items_for(conn, c.id)])
    if item:
        item_bank.save(conn, item)
        conn.commit()
        item_bank.append_jsonl(config.ITEMS_PATH, item)
    return item, log


def next_item(conn: sqlite3.Connection, graph: ConceptGraph, notes: NotesIndex, llm: LLM | None, student_id: str,
              entry: QueueEntry, exclude: set[str]) -> tuple[Item | None, str]:
    """Pick an unseen item for the queue entry; generate one if none are left (online), otherwise
    reuse the least-recently-relevant seen one. Returns (item, how) where how is bank/generated/repeat."""
    if unseen_count(conn, student_id, entry.concept_id) == 0 and llm is not None:
        item, _log = generate_for(conn, graph, notes, llm, student_id, entry)
        if item:
            return item, "generated"
    item = selector.pick_item(conn, student_id, entry.concept_id, exclude=exclude, misconception=entry.misconception)
    if item is None:
        return None, ""
    seen = conn.execute("SELECT 1 FROM responses WHERE student_id=? AND item_id=?", (student_id, item.id)).fetchone()
    return item, "repeat" if seen else "bank"
