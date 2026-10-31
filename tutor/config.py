"""Central configuration. Values come from environment variables / .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CONTENT_DIR = ROOT / "content"
DATA_DIR = ROOT / "data"
NOTES_DIR = ROOT / "notes"

CONCEPT_GRAPH_PATH = CONTENT_DIR / "concept_graph.yaml"
MISCONCEPTIONS_PATH = CONTENT_DIR / "misconceptions.yaml"
ITEMS_PATH = CONTENT_DIR / "items.jsonl"

APP_DB_PATH = Path(os.getenv("APP_DB_PATH", DATA_DIR / "app.db"))
SAMPLE_DB_PATH = DATA_DIR / "sample.db"
NOTES_INDEX_PATH = DATA_DIR / "notes_index.json"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL_LARGE = os.getenv("GROQ_MODEL_LARGE", "llama-3.3-70b-versatile")
MODEL_SMALL = os.getenv("GROQ_MODEL_SMALL", "llama-3.1-8b-instant")
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "0") == "1" or not GROQ_API_KEY
