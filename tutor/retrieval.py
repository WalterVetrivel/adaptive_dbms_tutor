"""BM25 retrieval over the course notes (no embeddings, no API calls).

`scripts/index_notes.py` turns the notes PDFs into `data/notes_index.json` (list of chunks).
At runtime we only load that JSON, so the PDFs never need to be deployed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from . import config

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set("""a an the of to in and or is are be for on with as by this that it its from at
which can will was were has have not but if then than so such these those into each any all""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


@dataclass(frozen=True)
class Chunk:
    id: int
    source: str   # file name
    unit: int | None
    page: int
    heading: str
    text: str


# ---- indexing ---------------------------------------------------------------

_HEADING = re.compile(r"^\s{0,8}((\d+(\.\d+)*\.?\s+)?[A-Z][A-Za-z0-9 ,&/()'\-–]{3,70}):?\s*$")


def _clean(s: str) -> str:
    s = s.replace("\x00", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def chunk_pdf(path: Path, max_words: int = 220) -> list[dict]:
    """Split a PDF into ~max_words chunks, remembering the most recent heading."""
    from pypdf import PdfReader

    unit_match = re.search(r"unit\s*[-_ ]?(\d)", path.name, re.I)
    unit = int(unit_match.group(1)) if unit_match else None
    chunks: list[dict] = []
    heading = ""
    buf: list[str] = []
    buf_page = 1

    def flush(page: int) -> None:
        nonlocal buf
        text = _clean("\n".join(buf))
        if len(text.split()) >= 25:
            chunks.append({"source": path.name, "unit": unit, "page": page, "heading": heading, "text": text})
        buf = []

    reader = PdfReader(str(path))
    for pno, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        for line in text.splitlines():
            if _HEADING.match(line) and len(line.split()) <= 9 and not line.strip().endswith("."):
                if sum(len(b.split()) for b in buf) > 60:
                    flush(buf_page)
                    buf_page = pno
                heading = line.strip().rstrip(":")
            buf.append(line)
            if sum(len(b.split()) for b in buf) >= max_words:
                flush(buf_page)
                buf_page = pno
    flush(buf_page)
    return chunks


def build_index(notes_dir: Path, out_path: Path) -> int:
    all_chunks: list[dict] = []
    for pdf in sorted(notes_dir.glob("*.pdf")):
        all_chunks.extend(chunk_pdf(pdf))
    for i, c in enumerate(all_chunks):
        c["id"] = i
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_chunks, ensure_ascii=False), encoding="utf-8")
    return len(all_chunks)


# ---- search -------------------------------------------------------------------

class NotesIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._bm25 = BM25Okapi([tokenize(c.heading + " " + c.text) for c in chunks]) if chunks else None

    @classmethod
    def load(cls, path: Path | None = None) -> "NotesIndex":
        path = path or config.NOTES_INDEX_PATH
        if not path.exists():
            return cls([])
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls([Chunk(**{k: c[k] for k in ("id", "source", "unit", "page", "heading", "text")}) for c in raw])

    def __len__(self) -> int:
        return len(self.chunks)

    def search(self, query: str, k: int = 3, unit: int | None = None, section_hint: str = "") -> list[Chunk]:
        """Top-k chunks. Chunks from `unit` and whose heading matches `section_hint` get a boost."""
        if not self._bm25:
            return []
        q = tokenize(query + " " + section_hint)
        if not q:
            return []
        scores = self._bm25.get_scores(q)
        hint_tokens = set(tokenize(section_hint))
        ranked = []
        for c, s in zip(self.chunks, scores):
            if unit is not None and c.unit is not None and c.unit != unit:
                s *= 0.5
            if hint_tokens and hint_tokens & set(tokenize(c.heading)):
                s *= 1.5
            ranked.append((s, c))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [c for s, c in ranked[:k] if s > 0]


@lru_cache(maxsize=1)
def get_index() -> NotesIndex:
    return NotesIndex.load()
