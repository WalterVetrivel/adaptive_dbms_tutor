# QueryMind: Adaptive DBMS Exam-Prep Tutor

An agentic AI tutor for **BE23CS405 Database Management System** that keeps a per-concept model of what each student understands. It diagnoses misconceptions from the student's *reasoning* (including the SQL they write), generates verified practice targeted at weak concepts, schedules spaced repetition, and shows teachers class-wide gaps.

Built for the Agentic AI Hackathon (October 2026), Problem 02. It runs on the **Groq free tier**.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # add your GROQ_API_KEY (optional: runs offline without it)

python scripts/build_sample_db.py   # data/sample.db: teaching database for SQL questions
python scripts/init_db.py           # data/app.db: app data
# copy the unit notes PDFs into notes/, then:
python scripts/index_notes.py       # data/notes_index.json: BM25 index over the notes

streamlit run app.py
python -m pytest -q
```

## Layout

```
app.py                 Streamlit entry point
tutor/                 core package
  config.py            settings from .env
  db.py                SQLite schema (students, items, responses, mastery, FSRS cards, LLM cache)
  llm.py               Groq client: model tiers, cache, 429 back-off, JSON validation
  graph.py             concept graph + misconception library loader (validated DAG)
  retrieval.py         BM25 search over the course notes
  viz.py               Graphviz concept map coloured by mastery
content/               concept_graph.yaml (63 concepts) · misconceptions.yaml (44)
scripts/               build_sample_db.py · init_db.py · index_notes.py
docs/                  plan, SRS, architecture, build plan, concept map
tests/                 pytest suite
```

## Build phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Skeleton, Groq client, schema, content, sample DB, notes index | ✅ |
| 2 | Verified item bank (SQL sandbox, FD tools, generator) | |
| 3 | Core logic (BKT, Elo, FSRS, selector, grader) | |
| 4 | Student UI + misconception/explainer agents | |
| 5 | Practice queue + spaced repetition | |
| 6 | Teacher dashboard + class simulator | |
| 7 | Polish, fallbacks, deploy | |

See [docs/](docs/) for the SRS and architecture.

Course materials (notes, textbooks, question banks) are git-ignored and stay local.
