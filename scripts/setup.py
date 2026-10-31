"""One-command setup: sample DB, app DB, verified seed bank, notes index (if PDFs present), demo class.

Usage: python scripts/setup.py [--no-class]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tutor import bootstrap, config, db, item_bank  # noqa: E402
from tutor.graph import get_graph  # noqa: E402
from tutor.retrieval import build_index  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-class", action="store_true", help="skip the simulated demo class")
    args = ap.parse_args()
    bootstrap.ensure_sample_db()
    print(f"✓ sample DB          {config.SAMPLE_DB_PATH}")
    conn = db.init_db()
    graph = get_graph()
    loaded, failures = item_bank.load_all(conn, graph, [p for p in (config.CONTENT_DIR / "seed_items.yaml",
                                                                    config.ITEMS_PATH) if p.exists()])
    print(f"✓ question bank      {loaded} verified items" + (f", {len(failures)} rejected" if failures else ""))
    pdfs = list(config.NOTES_DIR.glob("*.pdf"))
    if pdfs:
        n = build_index(config.NOTES_DIR, config.NOTES_INDEX_PATH)
        print(f"✓ notes index        {n} chunks from {len(pdfs)} PDFs")
    else:
        print("· notes index        skipped (put the unit notes PDFs in notes/ and re-run)")
    bootstrap.ensure_all(conn, graph, demo_class=False)
    if not args.no_class:
        made = bootstrap.ensure_demo_class(conn, graph)
        print("✓ demo class         " + ("25 simulated students" if made else "already present"))
    print("✓ Groq               " + ("OFFLINE (no GROQ_API_KEY): rule-based fallbacks" if config.OFFLINE_MODE
                                      else f"{config.MODEL_LARGE} / {config.MODEL_SMALL}"))
    print("\nRun:  streamlit run Home.py")
