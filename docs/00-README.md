# Adaptive DBMS Exam-Prep Tutor — Hackathon Docs

**Hackathon:** Agentic AI Hackathon, October 2026 — Problem 02
**Working name:** *QueryMind* (rename freely)
**Constraints:** solo builder · 7–8 hours · Database Management Systems syllabus · Groq free tier (no paid LLM APIs)

## The problem (from the brief)

> Generic AI tutors answer questions but don't track what a student actually understands.

Must build: (1) a diagnostic test; (2) a concept graph for one syllabus; (3) a learner model that updates mastery per concept after every answer; (4) question generation targeted at weak concepts, with difficulty calibration; (5) misconception detection from the reasoning in wrong answers; (6) spaced-repetition scheduling; (7) a teacher dashboard showing class-wide gaps.

## Documents

| File | What it covers |
|---|---|
| [01-solution-ideas.md](01-solution-ideas.md) | What to build, the DBMS concept graph, misconceptions, differentiators |
| [02-SRS.md](02-SRS.md) | Software Requirements Specification, scoped to a solo 8-hour MVP |
| [03-architecture-and-tech-stack.md](03-architecture-and-tech-stack.md) | Architecture, agents, algorithms, Groq free-tier strategy, stack |
| [04-build-plan.md](04-build-plan.md) | Hour-by-hour solo schedule, cut list, demo script, risks |
| [05-concept-map.md](05-concept-map.md) | DBMS concept map from the BE23CS405 syllabus and your notes: 63 concepts, 44 misconceptions |

## Requirement traceability

| Brief item | SRS | Component |
|---|---|---|
| Diagnostic test | FR-2 | Adaptive selector over the concept graph |
| Concept graph | FR-1 | `content/concept_graph.yaml` (built from the syllabus and notes) |
| Learner model | FR-3 | BKT per concept + prerequisite propagation (plain Python) |
| Targeted question gen + difficulty calibration | FR-4 | Generator agent + **SQL-execution verifier** + Elo calibration |
| Misconception detection from reasoning | FR-5 | Misconception Analyst agent + misconception library |
| Spaced repetition | FR-6 | FSRS (`fsrs` library) |
| Teacher dashboard | FR-7 | Streamlit teacher page + Class Insights agent |

## Reference material

- `syllabus/DBMS Syllabus.pdf`: BE23CS405, 5 units. This sets the concept graph's structure and Bloom levels.
- `notes/DBMS Unit 1–5 Notes.pdf`: used to ground question generation and explanations (BM25 retrieval). Each concept points to its notes section.
- `question_banks/`: 2-mark and 16-mark questions per unit, used as style seeds for generated questions.
- `textbooks/`: Silberschatz et al. and Elmasri–Navathe, for deeper explanations (too large to index whole, so only index chapters you need).
