# 03 — Software Architecture and Tech Stack

Scoped for **one developer, 8 hours, Groq free tier**.

## 1. Design principles

1. **Deterministic core, agentic edges.** Mastery maths, scheduling, item selection and grading are plain Python. LLM agents read reasoning, write questions, explain, and summarise.
2. **Verify with code, not with the LLM.** Running SQL and FD algorithms decide correctness. This is both more reliable and cheaper on rate limits.
3. **Spend free-tier tokens up front.** Pre-generate and verify the item bank in a batch script, cache every LLM response, and only call the LLM live for misconception analysis and explanations.
4. **One process, one language.** Streamlit + SQLite means no frontend build, no API layer, and no deployment headaches.

## 2. Architecture

```
┌──────────────────────── Streamlit app (app.py, pages/) ────────────────────────┐
│ Student: Diagnostic · Practice · My Progress     Teacher: Class · Drill-down   │
└───────────────┬────────────────────────────────────────────────────────────────┘
                │ direct Python calls
┌───────────────▼──────────────── tutor/ (Python package) ───────────────────────┐
│  orchestrator.py   on_answer(): grade → update model → diagnose → schedule      │
│                    → pick next item                                             │
│                                                                                 │
│  Deterministic core                         Agents (Groq, JSON mode)            │
│  ├─ graph.py        concept DAG (networkx)  ├─ misconception_agent.py           │
│  ├─ learner_model.py BKT + propagation      ├─ generator_agent.py               │
│  ├─ selector.py     diagnostic + practice   ├─ explainer_agent.py               │
│  ├─ scheduler.py    FSRS wrapper            ├─ insights_agent.py (teacher brief)│
│  ├─ calibration.py  Elo for items/students  └─ llm.py  Groq client: model       │
│  ├─ grader.py       MCQ / SQL / FD grading        tiering, cache, 429 backoff   │
│  ├─ sql_sandbox.py  read-only SQLite runner                                     │
│  ├─ fd_tools.py     closure, keys, normal form                                  │
│  ├─ schedule_tools.py precedence graph, 2PL / wait-die simulation               │
│  └─ retrieval.py    BM25 over your notes                                        │
└───────┬───────────────────────────────┬──────────────────────────┬─────────────┘
        │                               │                          │
   app.db (SQLite)               sample.db (read-only)        notes/ (your
   students, items, responses,   employees, departments,      DBMS notes, chunked
   mastery, cards, llm_cache     projects, enrolments…        and BM25-indexed)

Offline scripts: build_graph.py · generate_bank.py · simulate_class.py
```

## 3. Agents

| Agent | When it runs | Input | Output (JSON) | Groq model tier |
|---|---|---|---|---|
| **Misconception Analyst** | Live, on each wrong answer | Question, reference answer, student answer/SQL, SQL error or result diff, reasoning, candidate misconceptions for the concept | `{matches:[{id,confidence}], error_type, rationale}` | Large |
| **Explainer** | Live, after the analyst | Question, diagnosis, 1–2 retrieved note chunks | ≤ 80-word explanation + one contrast question | Small (fast) |
| **Question Generator** | Offline batch + on-demand top-up | Concept, difficulty band, target misconception, retrieved note chunks, sample DB schema, 2 example items | Item JSON (stem, options or reference SQL, answer, solution, distractor→misconception map) | Large |
| **MCQ Cross-checker** | After generating a theory MCQ | Item without the key | Chosen option + "ambiguous?" | Small |
| **Class Insights** | Teacher page (cached daily) | Heatmap aggregates + misconception counts | Re-teach brief: top 3 gaps, activities, students to watch | Large |
| **Graph Drafter** | One-off script | Your notes | Draft `concept_graph.yaml` for manual editing | Large |

The **orchestrator** is a plain Python state machine, not an LLM, which keeps it fast and predictable. The agentic part of the pitch is the loop: diagnose → update model → generate targeted practice → verify → schedule → report.

## 4. Groq free-tier strategy

- **Models (check current list and limits at console.groq.com/docs/models and /docs/rate-limits before starting):**
  - Large: `llama-3.3-70b-versatile` or `openai/gpt-oss-120b` for generation, misconception analysis, and the teacher brief.
  - Small: `llama-3.1-8b-instant` for explanations and MCQ cross-checks (much higher daily limits).
- **API:** Groq is OpenAI-compatible. Use the `groq` Python SDK (or `openai` with `base_url="https://api.groq.com/openai/v1"`), with `response_format={"type":"json_object"}` and `temperature` 0.2–0.4 for JSON tasks.
- **Budget protection:**
  - `llm_cache` table keyed by a hash of (model, prompt). Identical calls never repeat.
  - The item bank is generated once (≈ 100 calls) at the start of the day, not during the demo.
  - On HTTP 429: read `retry-after`, back off, then fall back to the other model tier.
  - Rule-based fallback for misconceptions: MCQ distractors carry misconception ids; regex patterns on SQL (aggregate in WHERE, `= NULL`, LEFT JOIN + WHERE on right table, missing GROUP BY column, comma join without condition).
  - Keep prompts small: send only the candidate misconceptions for the item's concept, not the whole library.
- Do not use Groq for embeddings (not needed). Retrieval uses BM25 (`rank_bm25`), which is free and instant.

## 5. Core algorithms

### 5.1 Learner model (BKT)
Per (student, concept): `p_init=0.3, p_learn=0.15, p_slip=0.1, p_guess=0.25` (MCQ) or `0.05` (SQL/FD).
```
if correct: post = p(1-s) / (p(1-s) + (1-p)g)
else:       post = p·s    / (p·s    + (1-p)(1-g))
p_new = post + (1-post)·p_learn
```
- Difficulty: hard items use lower guess and higher slip; easy items the opposite.
- Propagation: on a wrong answer, each prerequisite `q`: `p_q -= 0.3·(p_before − p_after)`, floor at 0.05.
- Every update writes a `mastery_events` row (before, after, cause).

### 5.2 Selection
- Diagnostic: concept with max `p(1-p)`, preferring prerequisites of the last wrong concept; one item per concept until 12 items.
- Practice: queue = due FSRS cards (~40%) + lowest-mastery concepts (~40%) + active misconceptions (~20%). Within a concept, pick the item whose Elo gives ≈ 70% predicted success.

### 5.3 Difficulty calibration (Elo)
```
expected = 1 / (1 + 10^((item_elo − student_concept_elo)/400))
item_elo    += K·(expected − correct)      # K = 24
student_elo += K·(correct − expected)
```
Initial item Elo: easy 1000, medium 1200, hard 1400. The simulator's synthetic responses calibrate items before the demo, so the "calibrated difficulty" shown is real.

### 5.4 Spaced repetition
`fsrs` Python package, one card per (student, concept). Grades: wrong → Again; correct but flawed reasoning or a hint used → Hard; correct → Good. The demo clock is an app-wide `now()` override.

### 5.5 SQL grading and verification
- `sample.db` opened with `sqlite3.connect("file:sample.db?mode=ro", uri=True)`; reject anything except a single `SELECT`/`WITH`; 2-second timeout via `set_progress_handler`.
- Correct when the student's result set equals the reference result set (compared as multisets of rows; ordered comparison only if the question requires ORDER BY).
- Generated SQL items are kept only if the reference query runs, returns 1–50 rows, and returns different results from the obvious wrong variant (proves the item is discriminating).
- The SQL error message and a row-diff summary are passed to the Misconception Analyst as evidence.

### 5.6 FD tools
Attribute closure, candidate keys (brute force over attribute subsets, fine for ≤ 7 attributes), and a highest-normal-form check (2NF/3NF/BCNF). These both verify generated FD questions and grade student answers.

### 5.7 Schedule tools
Builds a precedence graph from a schedule string (e.g. `r1(A) w2(A) r2(B) w1(B)`) to check conflict serializability (cycle test) and the equivalent serial order; simulates basic 2PL and wait-die/wound-wait to verify Unit 3 questions.

### 5.8 Misconception prompt (sketch)
```
System: You diagnose undergraduate DBMS students' errors. Judge the REASONING
and the submitted query, not only the final answer. Choose from the candidate
misconceptions only if the evidence supports it. If it is a typo, syntax slip
or misread question, say so. Respond with JSON:
{"matches":[{"id":str,"confidence":0..1}],"error_type":"conceptual|syntax|careless|misread","rationale":str}
User: <question> <reference answer> <student answer> <sql error / row diff> <student reasoning> <candidates>
```

## 6. Tech stack

| Layer | Choice | Why (solo, 8 h) |
|---|---|---|
| UI | **Streamlit** (multipage) | Student and teacher views in pure Python; no frontend build |
| Concept map | `st.graphviz_chart` (built in) or `streamlit-agraph` | Coloured DAG in a few lines |
| Charts | Plotly heatmap (`px.imshow`) | Teacher heatmap |
| LLM | **Groq free tier** via the `groq` SDK | Free and very fast; JSON mode |
| Storage | SQLite (`sqlite3` or SQLModel) | Zero setup |
| Graph | `networkx` + PyYAML | DAG validation, prerequisites |
| Spaced repetition | `fsrs` | Ready-made, credible algorithm |
| Retrieval | `rank_bm25`; `pypdf` if notes are PDFs | No embeddings needed |
| Validation | Pydantic v2 | Validate LLM JSON |
| Config | `python-dotenv` | `GROQ_API_KEY` in `.env` |
| Deploy | Local + Streamlit Community Cloud (free) | Shareable URL for judges |

`requirements.txt`: `streamlit groq pydantic networkx pyyaml fsrs rank_bm25 pypdf plotly python-dotenv`

## 7. Project layout
```
agentic_ai_hackathon_oct2026/
├─ app.py                     # Streamlit entry + sidebar user picker
├─ pages/ 1_Diagnostic.py · 2_Practice.py · 3_Progress.py · 4_Teacher.py
├─ tutor/                     # modules listed in §2
├─ content/ concept_graph.yaml · misconceptions.yaml · items.jsonl
├─ data/ sample.db · app.db
├─ notes/                     # your DBMS notes and references
├─ scripts/ build_graph.py · build_sample_db.py · generate_bank.py · simulate_class.py
├─ docs/                      # these documents
└─ .env                       # GROQ_API_KEY (never commit)
```

## 8. Sequence: student submits an answer
1. `grader.grade(item, answer)` → correct?, plus SQL error or row diff.
2. `learner_model.update()` + `calibration.update()` → mastery delta logged.
3. `scheduler.review()` → FSRS card updated.
4. If wrong: `misconception_agent.diagnose()` (cache → Groq large → rule fallback) → update student misconceptions.
5. `explainer_agent.explain()` with note chunks from `retrieval.search()`.
6. `selector.next_item()`; if the bank for that (concept, band, misconception) is empty, call `generator_agent` → verify → save → serve.
