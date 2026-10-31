"""Item bank: load seed/generated items from files, store them in SQLite, query them."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

from .graph import ConceptGraph
from .schemas import BAND_ELO, Item
from .verifier import verify


def load_seed_file(path: Path) -> list[Item]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Item(**{**r, "source": "seed"}).ensure_id() for r in raw["items"]]


def load_jsonl(path: Path) -> list[Item]:
    if not path.exists():
        return []
    return [Item.model_validate_json(line).ensure_id()
            for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, item: Item) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(item.model_dump_json(exclude_none=True) + "\n")


def _row(item: Item) -> tuple:
    extra = {k: v for k, v in {"fd_spec": item.fd_spec, "schedule_spec": item.schedule_spec,
                               "wrong_variants": item.wrong_variants}.items() if v}
    return (item.id, item.concept_id, item.type, item.difficulty_band, item.stem,
            json.dumps(item.options) if item.options else None, item.answer, item.reference_sql,
            item.solution, json.dumps({**item.misconception_map, **({"_extra": extra} if extra else {})}),
            item.target_misconception, BAND_ELO[item.difficulty_band], item.source, int(item.verified),
            item.verification_note)


def save(conn: sqlite3.Connection, item: Item) -> None:
    """Insert or update an item. Keeps the calibrated Elo and response count if it already exists."""
    conn.execute(
        """INSERT INTO items(id, concept_id, type, difficulty_band, stem, options_json, answer, reference_sql,
               solution, misconception_map_json, target_misconception, elo, source, verified, verification_note)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET stem=excluded.stem, options_json=excluded.options_json,
               answer=excluded.answer, reference_sql=excluded.reference_sql, solution=excluded.solution,
               misconception_map_json=excluded.misconception_map_json,
               target_misconception=excluded.target_misconception, verified=excluded.verified,
               verification_note=excluded.verification_note""",
        _row(item))


def from_row(row: sqlite3.Row) -> Item:
    mmap = json.loads(row["misconception_map_json"] or "{}")
    extra = mmap.pop("_extra", {})
    return Item(id=row["id"], concept_id=row["concept_id"], type=row["type"],
                difficulty_band=row["difficulty_band"], stem=row["stem"],
                options=json.loads(row["options_json"]) if row["options_json"] else None,
                answer=row["answer"], reference_sql=row["reference_sql"], solution=row["solution"] or "",
                misconception_map=mmap, target_misconception=row["target_misconception"],
                fd_spec=extra.get("fd_spec"), schedule_spec=extra.get("schedule_spec"),
                wrong_variants=extra.get("wrong_variants", []), source=row["source"],
                verified=bool(row["verified"]), verification_note=row["verification_note"] or "")


def get(conn: sqlite3.Connection, item_id: str) -> Item | None:
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return from_row(row) if row else None


def items_for(conn: sqlite3.Connection, concept_id: str, band: str | None = None,
              misconception: str | None = None, verified_only: bool = True) -> list[sqlite3.Row]:
    sql = "SELECT * FROM items WHERE concept_id=?"
    args: list = [concept_id]
    if band:
        sql += " AND difficulty_band=?"
        args.append(band)
    if misconception:
        sql += " AND (target_misconception=? OR misconception_map_json LIKE ?)"
        args += [misconception, f'%"{misconception}"%']
    if verified_only:
        sql += " AND verified=1"
    return conn.execute(sql, args).fetchall()


def counts(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for r in conn.execute("SELECT concept_id, difficulty_band, COUNT(*) n FROM items WHERE verified=1 "
                          "GROUP BY concept_id, difficulty_band"):
        out.setdefault(r["concept_id"], {})[r["difficulty_band"]] = r["n"]
    return out


def load_all(conn: sqlite3.Connection, graph: ConceptGraph, files: list[Path]) -> tuple[int, list[tuple[str, str]]]:
    """Verify and load items from seed YAML / generated JSONL files. Returns (#loaded, failures)."""
    loaded, failures = 0, []
    for f in files:
        items = load_seed_file(f) if f.suffix in (".yaml", ".yml") else load_jsonl(f)
        for item in items:
            ok, note = verify(item, graph)
            if ok:
                save(conn, item)
                loaded += 1
            else:
                failures.append((item.id, note))
    conn.commit()
    return loaded, failures
