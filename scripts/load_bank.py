"""Verify every item in content/seed_items.yaml and content/items.jsonl and load it into data/app.db."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tutor import config, db, item_bank  # noqa: E402
from tutor.graph import get_graph  # noqa: E402

if __name__ == "__main__":
    graph = get_graph()
    conn = db.init_db()
    files = [config.CONTENT_DIR / "seed_items.yaml", config.ITEMS_PATH]
    loaded, failures = item_bank.load_all(conn, graph, [f for f in files if f.exists()])
    print(f"Loaded {loaded} verified items.")
    for item_id, note in failures:
        print(f"  REJECTED {item_id}: {note}")
    counts = item_bank.counts(conn)
    core = graph.core_ids()
    missing = [c for c in core if c not in counts]
    print(f"Demo-core coverage: {len(core) - len(missing)}/{len(core)} concepts have items.")
    if missing:
        print("  No items yet:", ", ".join(missing))
