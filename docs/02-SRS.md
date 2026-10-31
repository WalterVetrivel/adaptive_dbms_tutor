# 02 — Software Requirements Specification (SRS)

**Product:** Adaptive DBMS Exam-Prep Tutor with a Learner Model (working name *QueryMind*)
**Version:** 0.2 (solo, 8-hour hackathon scope) · **Date:** 31 Oct 2026
**Format:** IEEE 830 / ISO 29148 structure, trimmed

Priority: **M** = must (MVP, needed for the demo) · **S** = should (if on schedule) · **C** = could (stretch)

---

## 1. Introduction

### 1.1 Purpose
Defines the requirements for an AI tutor that keeps a per-concept model of each student's understanding of Database Management Systems, uses it to diagnose, practise and schedule revision, and shows class-wide gaps to teachers.

### 1.2 Scope
In scope: one syllabus (BE23CS405 Database Management System, 5 units), a student UI, a teacher dashboard, LLM agents running on the Groq free tier, and a sample SQLite database for SQL questions.
Out of scope: real authentication, multi-tenant deployment, payments, mobile app, LMS integration, ER-diagram drawing questions.

### 1.3 Definitions
| Term | Meaning |
|---|---|
| Concept | Smallest teachable unit (e.g., "HAVING clause", "BCNF") |
| Concept graph | Directed acyclic graph of concepts with prerequisite edges |
| Mastery | Probability (0–1) that the student has learned a concept |
| Learner model | Per-student set of mastery values, misconception flags and review schedule |
| Misconception | A named recurring incorrect belief linked to concepts |
| Item | One question with answer key, concept tags, difficulty and metadata |
| Sample DB | A small SQLite database (e.g., employees/departments/projects, students/courses/enrolments) used to run SQL items |
| BKT / FSRS / Elo | Bayesian Knowledge Tracing / Free Spaced Repetition Scheduler / Elo rating for difficulty |

### 1.4 References
- Hackathon problem statement 02
- BE23CS405 Database Management System syllabus, KIOT Regulations 2023 (`syllabus/`)
- Unit 1–5 notes (`notes/`) and unit question banks (`question_banks/`)
- Textbooks: Silberschatz, Korth, Sudarshan, *Database System Concepts*; Elmasri, Navathe, *Fundamentals of Database Systems* (`textbooks/`)

## 2. Overall Description

### 2.1 Product perspective
A single Python application (Streamlit UI + Python modules) with SQLite storage. LLM calls go to Groq's OpenAI-compatible API on the free tier. Mastery maths, scheduling and grading are deterministic code.

### 2.2 Users
| User | Goals |
|---|---|
| Student (UG CS) | Find weak spots, practise efficiently, prepare for exams/GATE/interviews |
| Teacher | See class-wide gaps and misconceptions, decide what to re-teach |
| Builder/admin | Maintain the concept graph, misconception library and item bank |

### 2.3 Constraints
- C-1: One developer, 7–8 hours total build time.
- C-2: **Groq free tier only.** Requests-per-minute and tokens-per-day limits apply per model. No paid APIs.
- C-3: No real student data. The dashboard uses simulated students.
- C-4: Content must match the builder's DBMS notes.

### 2.4 Assumptions
- Groq API key available; free-tier limits are enough for one demo user plus a pre-generated item bank.
- The builder supplies notes as text, Markdown or PDF.
- The demo runs locally or on Streamlit Community Cloud.

## 3. Functional Requirements

### FR-1 Concept graph
| ID | Requirement | Pri |
|---|---|---|
| FR-1.1 | Store the BE23CS405 concept graph (63 concepts, 5 units, 74 prerequisite edges, 24 flagged demo-core) in `content/concept_graph.yaml`. | M |
| FR-1.2 | Each concept has: id, name, unit, Bloom level, description, prerequisite ids, allowed item types, demo-core flag, linked misconception ids, notes reference (file + section). | M |
| FR-1.3 | Validate on load that the graph is acyclic. | M |
| FR-1.4 | Render the graph coloured by mastery for the student and for the class average. | M |
| FR-1.5 | The diagnostic and the item bank cover demo-core concepts first; the rest are added when there is time. | M |

### FR-2 Diagnostic test
| ID | Requirement | Pri |
|---|---|---|
| FR-2.1 | A new student takes an adaptive diagnostic of 10–15 items. | M |
| FR-2.2 | Next concept = highest uncertainty `p(1-p)`, with priority for prerequisites of concepts just answered wrongly. | M |
| FR-2.3 | Every item asks for an answer and a one-line reasoning (SQL items: the query is the reasoning, and a "why" is optional). | M |
| FR-2.4 | At the end, show the mastery map and the top-3 focus concepts. | M |

### FR-3 Learner model
| ID | Requirement | Pri |
|---|---|---|
| FR-3.1 | Maintain P(mastery) per (student, concept), initialised from a prior. | M |
| FR-3.2 | Update mastery with BKT after **every** answer. | M |
| FR-3.3 | Item difficulty modulates the update (correct on a hard item = stronger evidence). | S |
| FR-3.4 | A wrong answer lowers immediate prerequisites by a damped amount (one hop). | S |
| FR-3.5 | Store active misconceptions per student with confidence and evidence. | M |
| FR-3.6 | Log every mastery change (before, after, cause) for explainability. | M |

### FR-4 Question generation and difficulty calibration
| ID | Requirement | Pri |
|---|---|---|
| FR-4.1 | Generate items targeted at a concept, a difficulty band (easy/medium/hard) and optionally a misconception. | M |
| FR-4.2 | Item types: MCQ (4 options); "write the SQL"; short answer for FDs (closure, candidate keys, highest normal form). | M (MCQ, SQL) / S (FD) |
| FR-4.3 | Generation is grounded in retrieved chunks of the builder's notes. | M |
| FR-4.4 | **SQL items** are served only if the reference query executes on the sample DB and returns a non-empty result. Student SQL is graded by comparing result sets (order-insensitive unless ORDER BY is required). | M |
| FR-4.5 | **FD items** are checked by a Python closure / candidate-key / normal-form routine. | S |
| FR-4.6 | MCQs are checked by a second, independent LLM call that answers without the key; disagreements are discarded. | S |
| FR-4.7 | Each item has an initial difficulty (easy/medium/hard → Elo 1000/1200/1400), updated by Elo after each response. | M |
| FR-4.8 | The selector targets ≈ 70% predicted success for the student. | S |
| FR-4.9 | A bank of ~60–100 verified items is pre-generated before the demo; on-demand generation tops it up. | M |

### FR-5 Misconception detection
| ID | Requirement | Pri |
|---|---|---|
| FR-5.1 | Misconception library of 44 seeded entries (`content/misconceptions.yaml`) (id, description, concepts, example wrong reasoning, remediation). | M |
| FR-5.2 | For each wrong answer, analyse the reasoning / submitted SQL (and SQL error message or result diff) and return JSON: misconception ids + confidence, error type (conceptual / syntax / careless / misread), rationale. | M |
| FR-5.3 | Mark a misconception *active* at confidence ≥ 0.7 or on 2 occurrences; *resolved* after 2 later correct answers on items targeting it. | M |
| FR-5.4 | Validate the JSON output; retry once; otherwise record "unclassified". | M |
| FR-5.5 | Show a short targeted explanation after a wrong answer, with a reference to the notes. | M |
| FR-5.6 | Flag "right answer, wrong reasoning" on correct answers. | C |

### FR-6 Spaced repetition
| ID | Requirement | Pri |
|---|---|---|
| FR-6.1 | One FSRS card per (student, concept), storing stability, difficulty and due date. | M |
| FR-6.2 | Map each answer to a grade: wrong → Again, correct with weak reasoning → Hard, correct → Good. | M |
| FR-6.3 | Today's queue mixes due reviews, the weakest concepts and active misconceptions. | M |
| FR-6.4 | A demo-only "advance clock by N days" control. | M |

### FR-7 Teacher dashboard
| ID | Requirement | Pri |
|---|---|---|
| FR-7.1 | Class × concept mastery heatmap. | M |
| FR-7.2 | Top misconceptions with counts and affected students. | M |
| FR-7.3 | Student drill-down: mastery, misconceptions, recent answers with reasoning. | M |
| FR-7.4 | AI "what to re-teach" brief from aggregated data (cached). | S |
| FR-7.5 | A simulator script creates ~25 students with personas and answer histories. | M |

### FR-8 Users
| ID | Requirement | Pri |
|---|---|---|
| FR-8.1 | A sidebar selector to pick a student or the teacher view (no real auth). | M |

## 4. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | Performance | Grading + mastery update ≤ 300 ms. LLM feedback ≤ 3 s typical (Groq is fast). |
| NFR-2 | Free-tier budget | The demo must run within Groq free-tier limits: pre-generate items, cache all LLM results, use the small model for high-volume calls, back off and retry on HTTP 429. |
| NFR-3 | Resilience | If Groq is unavailable or rate-limited, serve items from the bank and fall back to rule-based misconception tags (MCQ distractor → misconception map; SQL error patterns → misconception). |
| NFR-4 | Correctness | 100% of served SQL items pass execution checks; theory MCQs spot-checked (20 items) before the demo. |
| NFR-5 | Explainability | Every mastery value and misconception flag can show its evidence. |
| NFR-6 | Privacy | Simulated students only; the student answer text is the only user content sent to the LLM. |
| NFR-7 | Safety | The sample DB is opened read-only for student queries; only a single SELECT statement is allowed; queries time out after 2 s. |
| NFR-8 | Portability | `pip install -r requirements.txt && streamlit run app.py`; API key read from `.env`. |

## 5. Interfaces

- **UI (Streamlit pages):** Student — Diagnostic, Practice, My Progress. Teacher — Class Overview, Student Drill-down.
- **Groq API:** OpenAI-compatible chat completions with JSON mode.
- **SQLite:** `app.db` (app data) and `sample.db` (read-only teaching database).

## 6. Data (SQLite tables)

`concepts`, `edges`, `misconceptions`, `items` (id, concept_id, type, stem, options, answer, reference_sql, difficulty_band, elo, misconception_map, source, verified), `students`, `responses` (student_id, item_id, answer, reasoning, correct, sql_error, created_at), `diagnoses` (response_id, misconception_id, confidence, error_type, rationale), `mastery`, `mastery_events`, `review_cards`, `student_misconceptions`, `llm_cache` (prompt_hash, response).

## 7. Demo Acceptance Criteria

1. A new student finishes the diagnostic in ≤ 12 items and sees a coloured concept map.
2. A wrong SQL answer that uses WHERE with an aggregate is tagged MC-AGG-01, and the next practice item targets HAVING.
3. Mastery visibly changes after every answer, and the evidence log shows why.
4. A freshly generated SQL question shows "verified by execution ✓".
5. After "advance clock 3 days", due reviews appear in Today's practice.
6. The teacher view shows the heatmap, the top 5 misconceptions and the re-teach brief for 25 simulated students.
