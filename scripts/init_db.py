"""Create data/app.db with the full schema (safe to re-run)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tutor import config, db  # noqa: E402

if __name__ == "__main__":
    db.init_db()
    print(f"Initialised {config.APP_DB_PATH}")
