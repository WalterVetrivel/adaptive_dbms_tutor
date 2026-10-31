"""Create a simulated class of 25 persona-driven students with ~10 days of history.

Uses the real pipeline (grading, BKT, Elo, FSRS, rule-based misconception detection); no LLM calls.
Usage: python scripts/simulate_class.py [--days 10] [--seed 7]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tutor import config, db, item_bank  # noqa: E402
from tutor.graph import get_graph  # noqa: E402
from tutor.simulation import simulate_class  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    conn = db.init_db()
    graph = get_graph()
    if not item_bank.counts(conn):
        item_bank.load_all(conn, graph, [p for p in (config.CONTENT_DIR / "seed_items.yaml", config.ITEMS_PATH)
                                         if p.exists()])
    counts = simulate_class(conn, graph, args.days, args.seed)
    print(f"Simulated {len(counts)} students, {sum(counts.values())} answers.")
    from tutor import analytics
    ids = list(counts)
    for m in analytics.misconception_stats(conn, ids)[:5]:
        print(f"  {m.misconception_id}: {len(m.active)} active, {len(m.suspected)} suspected")
