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
python scripts/load_bank.py         # verify + load the 56 seed questions
python scripts/generate_bank.py     # optional, needs GROQ_API_KEY: generate more verified questions
python scripts/simulate_class.py    # demo class: 25 persona-driven students, ~1,500 answers

streamlit run Home.py
python -m pytest -q
```

## Layout

```
Home.py                Streamlit entry point (home page)
tutor/                 core package
  config.py            settings from .env
  db.py                SQLite schema (students, items, responses, mastery, FSRS cards, LLM cache)
  llm.py               Groq client: model tiers, cache, 429 back-off, JSON validation
  graph.py             concept graph + misconception library loader (validated DAG)
  retrieval.py         BM25 search over the course notes
  viz.py               Graphviz concept map coloured by mastery
  schemas.py           Item model
  sql_sandbox.py       read-only SQL runner, result comparison, SQL item verification
  fd_tools.py          closure, candidate keys, normal forms, lossless/preserving checks
  schedule_tools.py    precedence graph, conflict serializability, recoverable/cascadeless
  verifier.py          code-based verification for every item type
  item_bank.py         load/save/query items
  agents/generator.py  Question Generator agent (generate → verify → MCQ cross-check)
  learner_model.py     BKT mastery per concept + difficulty/reasoning modulation + graph propagation
  calibration.py       Elo for item difficulty and student ability
  scheduler.py         FSRS spaced repetition (one card per student × concept)
  selector.py          adaptive diagnostic + daily practice queue + 70%-success item picking
  grader.py            deterministic grading for MCQ / SQL / FD / schedule items
  rules.py             rule-based misconception detection (MCQ distractors, SQL patterns)
  misconception_tracker.py  suspected → active → resolved per student
  orchestrator.py      on-answer pipeline tying it all together
  clock.py · students.py
  agents/analyst.py    Misconception Analyst agent (reads reasoning + SQL error/row diff; keeps strong rule hits)
  agents/explainer.py  Explainer agent (≤80 words, notes-grounded, contrast question; offline fallback)
  analytics.py         class aggregates (heatmap matrix, gaps, misconception stats, at-risk students)
  simulation.py        persona-driven simulated students answering through the real pipeline
  agents/insights.py   Class Insights agent ('what to re-teach' brief; cached daily; offline fallback)
  practice.py          practice session: queue → items, on-demand generation, streak
  ui.py                shared Streamlit components (incl. demo clock control)
pages/                 1 Diagnostic · 2 Practice · 3 Progress · 4 Teacher
content/               concept_graph.yaml (63 concepts) · misconceptions.yaml (44) · seed_items.yaml (56) · items.jsonl (generated)
scripts/               build_sample_db.py · init_db.py · index_notes.py · load_bank.py · generate_bank.py · simulate_class.py
docs/                  plan, SRS, architecture, build plan, concept map
tests/                 pytest suite
```

## Build phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Skeleton, Groq client, schema, content, sample DB, notes index | ✅ |
| 2 | Verified item bank (SQL sandbox, FD tools, generator) | ✅ |
| 3 | Core logic (BKT, Elo, FSRS, selector, grader) | ✅ |
| 4 | Student UI + misconception/explainer agents | ✅ |
| 5 | Practice queue + spaced repetition | ✅ |
| 6 | Teacher dashboard + class simulator | ✅ |
| 7 | Polish, fallbacks, deploy | |

See [docs/](docs/) for the SRS and architecture.

Course materials (notes, textbooks, question banks) are git-ignored and stay local.
