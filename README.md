# QueryMind: Adaptive DBMS Exam-Prep Tutor

An agentic AI tutor for **BE23CS405 Database Management System** that keeps a per-concept model of what each student understands. It diagnoses misconceptions from the student's *reasoning* (including the SQL they write), generates verified practice targeted at weak concepts, schedules spaced repetition, and shows teachers class-wide gaps.

Built for the Agentic AI Hackathon (October 2026), Problem 02. It runs on the **Groq free tier**.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # add your GROQ_API_KEY (optional: everything works offline with rule-based fallbacks)
# optional: copy the unit notes PDFs into notes/ (for notes-grounded explanations)
python scripts/setup.py         # sample DB, verified question bank, notes index, simulated class of 25
streamlit run Home.py
```

The app also bootstraps itself on first run, so `streamlit run Home.py` on a fresh clone works too.

Other scripts:

```bash
python scripts/generate_bank.py --per-band 1     # needs GROQ_API_KEY: grow the bank with verified AI questions
python scripts/simulate_class.py --days 10       # rebuild the simulated class
python -m pytest -q                              # 49 tests, no API key needed
```

## How it covers the brief

| Brief requirement | Where |
|---|---|
| Diagnostic test | 🩺 Diagnostic page: 12 adaptive questions over the concept graph; probes prerequisites after a wrong answer (`selector.py`) |
| Concept graph for one syllabus | `content/concept_graph.yaml`: BE23CS405, 63 concepts, 5 units, 74 prerequisite edges, validated DAG |
| Learner model updated after every answer | `learner_model.py`: BKT per concept, difficulty- and reasoning-aware, propagates to prerequisites; evidence log on 📈 Progress |
| Targeted question generation + difficulty calibration | `agents/generator.py` generates for weak concepts/misconceptions; SQL verified by execution, FD/schedule answers computed by algorithms; Elo calibration with predicted success shown on every question |
| Misconception detection from reasoning | `agents/analyst.py` reads the student's "why" + their SQL/error/row diff; 44-entry library; rule fallback (`rules.py`) |
| Spaced repetition | `scheduler.py` (FSRS); 🏋️ Practice queue mixes due reviews, weak concepts and misconceptions; demo clock |
| Teacher dashboard | 👩‍🏫 Teacher page: heatmap, top misconceptions, weakest concepts, AI re-teach brief, student drill-down |

## Demo script (3 minutes)

1. **Home → Demo controls → Reset demo.** Riya starts fresh.
2. **🩺 Diagnostic:** answer 4–5 questions. The unit map colours in. Get one wrong and the next question checks its prerequisite.
3. **The key moment:** on a GROUP BY question, write `... WHERE COUNT(*) > 5 GROUP BY ...` with the reason "WHERE filters the rows I want". You get a SQLite error, the **WHERE-vs-HAVING** misconception, a mastery drop that propagates to *SQL aggregate functions*, a targeted explanation, and an excerpt from the notes.
4. **🏋️ Practice:** the queue leads with "🧠 Fixing a misconception". Questions show *verified by execution* and *predicted success*.
5. **Demo clock +3d:** "Reviews due" jumps and 🔁 review items lead the queue.
6. **👩‍🏫 Teacher:** "WHERE can filter on aggregate results" held by about 8 students in the brief and misconceptions table; heatmap; drill into Bhavya R to see the actual reasoning.
7. **Trust:** every SQL question is checked by running it, FD and schedule answers are computed by algorithms, everything runs on Groq's free tier, and it all still works if Groq is down.

## Deploy (Streamlit Community Cloud, free)

1. Push to GitHub and create an app at share.streamlit.io with main file `Home.py`.
2. In *Secrets*, add `GROQ_API_KEY = "gsk_..."`. Streamlit exposes top-level secrets as environment variables.
3. First load builds the sample DB, question bank and demo class automatically (~5 s).
4. Notes PDFs aren't in the repo (copyright). Without `data/notes_index.json` the app works, but explanations won't quote the notes. Commit that file only if you're allowed to publish the notes text.

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
  clock.py · students.py · bootstrap.py (first-run setup, demo reset)
  agents/analyst.py    Misconception Analyst agent (reads reasoning + SQL error/row diff; keeps strong rule hits)
  agents/explainer.py  Explainer agent (≤80 words, notes-grounded, contrast question; offline fallback)
  analytics.py         class aggregates (heatmap matrix, gaps, misconception stats, at-risk students)
  simulation.py        persona-driven simulated students answering through the real pipeline
  agents/insights.py   Class Insights agent ('what to re-teach' brief; cached daily; offline fallback)
  practice.py          practice session: queue → items, on-demand generation, streak
  ui.py                shared Streamlit components (incl. demo clock control)
pages/                 1 Diagnostic · 2 Practice · 3 Progress · 4 Teacher
content/               concept_graph.yaml (63 concepts) · misconceptions.yaml (44) · seed_items.yaml (56) · items.jsonl (generated)
scripts/               setup.py · build_sample_db.py · init_db.py · index_notes.py · load_bank.py · generate_bank.py · simulate_class.py
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
| 7 | Polish, fallbacks, deploy | ✅ |

See [docs/](docs/) for the SRS and architecture.

Course materials (notes, textbooks, question banks) are git-ignored and stay local.
