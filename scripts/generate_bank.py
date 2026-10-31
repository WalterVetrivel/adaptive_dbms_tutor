"""Top up the item bank with LLM-generated, code-verified items.

Usage:
  python scripts/generate_bank.py                    # demo-core concepts, 1 item per band, if missing
  python scripts/generate_bank.py --per-band 2 --concepts sql_joins bcnf
  python scripts/generate_bank.py --all              # every concept

Generated items are appended to content/items.jsonl (commit it) and loaded into data/app.db.
Respect the Groq free tier: everything is cached, and the script stops early on repeated failures.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tutor import config, db, item_bank  # noqa: E402
from tutor.agents.generator import generate_item  # noqa: E402
from tutor.graph import get_graph  # noqa: E402
from tutor.llm import LLM  # noqa: E402
from tutor.retrieval import get_index  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concepts", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--per-band", type=int, default=1)
    ap.add_argument("--max-calls", type=int, default=120, help="stop after this many generations")
    args = ap.parse_args()

    if config.OFFLINE_MODE:
        sys.exit("No GROQ_API_KEY set (or OFFLINE_MODE=1). Add your key to .env to generate items; "
                 "the seed bank still works offline.")
    graph, notes = get_graph(), get_index()
    conn = db.init_db()
    llm = LLM(conn)
    concepts = args.concepts or (list(graph.concepts) if args.all else graph.core_ids())
    made = failed = calls = 0
    consecutive_fail = 0
    for cid in concepts:
        c = graph.concepts[cid]
        for band in ("easy", "medium", "hard"):
            existing = item_bank.items_for(conn, cid, band)
            need = args.per_band - len(existing)
            for i in range(max(0, need)):
                if calls >= args.max_calls or consecutive_fail >= 5:
                    print("Stopping early (call budget or repeated failures).")
                    return _report(made, failed, llm)
                item_type = c.item_types[(len(existing) + i) % len(c.item_types)]
                mcs = list(c.misconceptions)
                target = mcs[(len(existing) + i) % len(mcs)] if mcs else None
                calls += 1
                item, log = generate_item(llm, graph, notes, cid, item_type, band, target,
                                          avoid=[r["stem"] for r in item_bank.items_for(conn, cid)])
                if item:
                    item_bank.save(conn, item)
                    conn.commit()
                    item_bank.append_jsonl(config.ITEMS_PATH, item)
                    made += 1
                    consecutive_fail = 0
                    print(f"  + {cid} [{band}/{item_type}] {item.stem[:70]}")
                else:
                    failed += 1
                    consecutive_fail += 1
                    print(f"  x {cid} [{band}/{item_type}] rejected: {log}")
    _report(made, failed, llm)


def _report(made: int, failed: int, llm: LLM) -> None:
    print(f"Generated {made} verified items, {failed} rejected. LLM usage: {llm.usage_summary()}")


if __name__ == "__main__":
    main()
