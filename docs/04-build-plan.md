# 04 — Build Plan (solo, 7–8 hours)

Rule of thumb: **get the full loop working ugly by hour 4, then make it good.** Any feature not working by its checkpoint gets cut (see §3).

## 1. Before you start (15 min, can be done the night before)
- [x] Syllabus, notes, question banks and textbooks are in place; the concept graph and misconception library are built.
- [ ] Get a Groq API key, check the current free-tier limits per model, and put the key in `.env`.
- [ ] `python -m venv .venv && pip install streamlit groq pydantic networkx pyyaml fsrs rank_bm25 pypdf plotly python-dotenv`
- [ ] Make a Streamlit hello-world that calls Groq once in JSON mode.

## 2. Hour-by-hour schedule

| Time | Build | Checkpoint |
|---|---|---|
| **0:00–0:30** | Project skeleton (layout in 03 §7), `llm.py` (Groq client with cache, model tiers, 429 backoff), SQLite schema | One cached Groq JSON call works |
| **0:30–1:30** | **Content.** `concept_graph.yaml` and `misconceptions.yaml` are already done (see 05-concept-map.md), so spend 10 minutes reviewing them. Index the 5 unit notes PDFs for BM25 (`pypdf`, chunk by heading). `build_sample_db.py`: employees/departments/projects with ~50 rows, including some NULLs and unmatched rows on purpose (they make NULL/JOIN misconceptions testable). | Graph loads and is acyclic; sample DB queries work |
| **1:30–2:30** | **Item bank.** `sql_sandbox.py`, `fd_tools.py`, `generator_agent.py`, `generate_bank.py`: ~3 items per **demo-core** concept (24 × 3 ≈ 72; easy/medium/hard), using the question banks as style seeds, SQL verified by execution, FD verified by code, MCQs cross-checked. Let it run in the background while you do the next step. | ≥ 60 verified items in `items.jsonl` |
| **2:30–3:30** | **Core logic.** `learner_model.py` (BKT + propagation + event log), `calibration.py` (Elo), `scheduler.py` (FSRS), `selector.py`, `grader.py`. Quick pytest for BKT and SQL grading. | Answering an item in a script updates mastery and the FSRS card |
| **3:30–4:30** | **Student UI.** Sidebar user picker, Diagnostic page (question card, "why?" box, SQL text area), feedback card, mastery map with graphviz. Wire up `misconception_agent.py` + `explainer_agent.py` + rule fallback. | **Full loop works end-to-end** (diagnostic → feedback → map) |
| **4:30–5:30** | **Practice + spaced repetition.** Today's queue (due + weak + misconception), "advance clock" control, on-demand generation when the bank runs out, "verified ✓ / difficulty" badges. | Wrong HAVING answer → next item targets HAVING |
| **5:30–6:30** | **Teacher dashboard.** `simulate_class.py` (25 students with personas, e.g. "NULL-confused", "normalization-weak", "strong SQL", answering through the real pipeline with rule-based diagnosis to save tokens). Heatmap, top misconceptions, drill-down, Class Insights brief (one cached call). | Dashboard populated |
| **6:30–7:15** | **Polish + resilience.** Demo with Groq turned off (fallback works?), fix rough edges, nicer colours, README with run instructions, deploy to Streamlit Community Cloud. | Deployed URL works |
| **7:15–8:00** | **Demo prep.** Rehearse the script below twice and record a backup video. Slide: problem → loop diagram → numbers (items verified, misconception tags, calls/tokens used). | Ready to present |

## 3. Cut list (cut in this order if behind)
1. Class Insights AI brief → replace with a static "top 3 gaps" list computed in Python.
2. On-demand generation → serve from the pre-generated bank only (generation is still shown in the pitch via the bank script).
3. FD-type questions → keep MCQ + SQL only.
4. Prerequisite propagation → plain BKT.
5. MCQ cross-check → spot-check by hand instead.

**Never cut** (these are the brief's required items): diagnostic, concept graph, per-answer mastery update, targeted generation with difficulty, reasoning-based misconception detection, spaced repetition, teacher dashboard.

## 4. Demo script (3 minutes)
1. **Problem (15 s):** "Ask a chatbot for help with SQL and it fixes your query. It never notices that you think WHERE can filter on COUNT(*), and it won't remember tomorrow."
2. **Diagnostic (40 s):** a fresh student answers ~5 items; the concept map colours in; after a wrong answer on BCNF, the tutor jumps to check candidate keys.
3. **The key moment (45 s):** the student writes `WHERE COUNT(*) > 5`. The tutor runs it, tags **WHERE vs HAVING**, HAVING mastery drops on screen, a short explanation cites the notes, and a freshly generated, **execution-verified** HAVING question appears.
4. **Spaced repetition (15 s):** advance the clock 3 days → due reviews appear.
5. **Teacher (45 s):** heatmap shows the class is weak on Normalization and NULL handling; "9 of 25 students hold the WHERE-vs-HAVING misconception"; re-teach brief.
6. **Trust and cost (20 s):** "Every SQL question is verified by running it, FD answers are checked by an algorithm, and the whole thing runs on Groq's free tier: N LLM calls today."

## 5. Risks and mitigations
| Risk | Mitigation |
|---|---|
| Groq rate limits hit during the demo | Bank pre-generated; LLM cache; small model for explanations; rule-based fallback; rehearse with the API disabled |
| Groq returns malformed JSON | JSON mode + Pydantic validation + one retry + fallback |
| Generated SQL questions are wrong or ambiguous | Execution check + "discriminates from the wrong variant" check; drop failures |
| Concept graph takes too long | Already built from the syllabus (63 concepts); only demo-core is needed for the demo |
| Student SQL is dangerous | Read-only connection, SELECT-only, 2 s timeout |
| Running out of time | Checkpoints + cut list; the loop must work by 4:30 |

## 6. Definition of done
- [ ] All 7 brief items visible in the running app
- [ ] SRS §7 acceptance criteria pass
- [ ] Works with Groq unavailable (degraded but usable)
- [ ] Deployed link + backup video
- [ ] README with setup steps and an architecture diagram
