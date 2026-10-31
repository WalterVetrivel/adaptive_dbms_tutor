"""Build data/notes_index.json from the PDFs in notes/.

Usage: python scripts/index_notes.py [notes_dir]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tutor import config  # noqa: E402
from tutor.retrieval import build_index  # noqa: E402

if __name__ == "__main__":
    notes_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else config.NOTES_DIR
    n = build_index(notes_dir, config.NOTES_INDEX_PATH)
    print(f"Indexed {n} chunks from {notes_dir} -> {config.NOTES_INDEX_PATH}")
