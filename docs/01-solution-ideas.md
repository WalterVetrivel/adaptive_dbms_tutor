# 01 — Solution Ideas: What We Could Build

## 1. The pitch

Generic AI tutors are stateless. **QueryMind keeps a live model of what each student understands about databases**, concept by concept, and every agent decision follows from it: what to ask next, how hard, what to revise, and what to tell the teacher.

Pitch line: **"It doesn't just mark your SQL wrong — it figures out *why* you wrote it."**

## 2. Why DBMS is a great fit (use this in the pitch)

- **Answers are machine-checkable.** SQL questions can be verified by *actually running* the query against a sample SQLite database. Functional-dependency questions (closures, candidate keys, normal forms) can be verified by a few lines of Python. This lets the system verify generated questions without trusting the LLM, and judges usually ask about that.
- **Misconceptions are well known and specific** (NULL handling, WHERE vs HAVING, 3NF vs BCNF, 2PL and deadlocks). They are easy to name, detect, and show on a dashboard.
- **Clear prerequisite structure** (keys → FDs → closure → candidate keys → normal forms), so the concept graph means something.
- Relevant to every CS undergrad (university exams, GATE, placement interviews).

## 3. What to build (solo, 8 hours)

One Streamlit web app with two modes:

**Student mode**
1. **Diagnostic (~12 questions):** walks the concept graph adaptively. A wrong answer sends it to the prerequisite concept to check.
2. **Every answer asks "why?"** (one line). For SQL questions, the student's own query is the reasoning.
3. **Feedback card:** correct/incorrect, detected misconception (if any), a short targeted explanation, and a "from your notes" reference.
4. **Concept map** coloured red/amber/green by mastery, updating after every answer.
5. **Today's practice:** spaced-repetition reviews that are due plus new questions generated for the weakest concepts and active misconceptions.

**Teacher mode**
1. Class × concept mastery heatmap (seeded with ~25 simulated students).
2. Top misconceptions with the number of students affected.
3. Student drill-down showing mastery and recent answers with reasoning.
4. AI-written "what to re-teach" brief.

## 4. Scope: MVP vs stretch

| Area | MVP (must demo) | Stretch (only if ahead of schedule) |
|---|---|---|
| Syllabus | 24 demo-core concepts across all 5 units (items seeded) | All 63 concepts seeded with items |
| Question types | MCQ + "write the SQL" + FD/normal-form short answer | Schedule questions (conflict-serializable?) checked by code, ER diagram questions |
| Diagnostic | Adaptive, ~12 items | Early stopping by uncertainty |
| Learner model | BKT + one-hop prerequisite propagation | Mastery decay from FSRS retrievability |
| Question gen | Pre-generated bank (~80 items) + on-demand generation | Distractors built from misconceptions |
| Verification | SQL executed on a sample DB; FD answers checked in Python | LLM cross-check for theory MCQs |
| Misconceptions | ~20 seeded library entries; LLM classifies the reasoning | Agent proposes new misconceptions |
| Spaced repetition | FSRS per concept + "advance clock" button for the demo | Exam-date compression |
| Teacher dashboard | Heatmap, top misconceptions, drill-down | AI brief, CSV export |

## 5. Concept graph

See **[05-concept-map.md](05-concept-map.md)** for the full map built from the BE23CS405 syllabus and your unit notes. It has 63 concepts across 5 units, 74 prerequisite edges, and 24 "demo core" concepts to seed first.

| Unit | Title | Concepts (core) |
|---|---|---|
| 1 | Introduction to Relational Database: keys, constraints, relational algebra, SQL basics, DDL/DML | 12 (5) |
| 2 | Database Design: ER, FDs, decomposition, 1NF–5NF, set ops, aggregates, GROUP BY/HAVING, joins, subqueries, views, triggers | 19 (10) |
| 3 | Transaction Management: ACID, schedules, serializability, locking, 2PL, deadlock, isolation, recovery, DCL/TCL | 13 (5) |
| 4 | Implementation Techniques: RAID, file organization, indices, B+/B trees, hashing, query processing/optimization | 9 (2) |
| 5 | Advanced Topics: distributed DBs, 2PC/3PC, NoSQL, CAP, security, access control, SQL injection | 10 (2) |

## 6. Misconception library

There are 44 seeded misconceptions covering all five units, in `content/misconceptions.yaml` and listed in 05-concept-map.md. Some examples: `NULL = NULL` is TRUE; WHERE vs HAVING; LEFT JOIN + WHERE on the right table; every superkey is a candidate key; 3NF = BCNF; 2PL prevents deadlocks; READ COMMITTED prevents non-repeatable reads; a secondary index can be sparse; RAID 0 gives redundancy; 2PC never blocks; CAP all three at once.

## 7. Example interaction (the demo moment)

> **Q (Elo 1180, concept: HAVING):** Write a query listing departments with more than 5 employees.
> **Student:** `SELECT dept FROM emp WHERE COUNT(*) > 5 GROUP BY dept;` *Why:* "WHERE filters the rows I want."
> **Grader:** runs it on the sample DB → SQLite error: "misuse of aggregate".
> **Misconception Analyst:** matches **MC-AGG-01** (WHERE vs HAVING), confidence 0.93, error type: conceptual.
> **Learner model:** HAVING 0.52 → 0.31; GROUP BY prerequisite lowered slightly; the next question checks GROUP BY.
> **Tutor:** "WHERE filters rows *before* grouping, so the counts don't exist yet. Use HAVING, which filters groups *after* GROUP BY." + a contrast question + a reference to your notes.
> **Teacher dashboard:** MC-AGG-01 now affects 9 of 25 students → top of the re-teach list.

## 8. Differentiators

1. **Verification by execution:** generated SQL questions are only served if the reference query runs and returns a non-empty, deterministic result on the sample DB. FD answers are checked by a closure algorithm. The LLM does not get to decide what's correct.
2. **Reasoning-aware diagnosis:** the student's SQL itself is evidence. A wrong query reveals *which* misconception, unlike a plain wrong MCQ choice.
3. **Grounded in the course's own notes:** questions and explanations retrieve from your notes, so they match the syllabus and terminology.
4. **Runs on a free LLM tier:** model tiering, caching and pre-generation keep the system inside Groq's free limits. That is a real-world cost story.
5. **Explainable learner model:** every mastery change is logged with its cause.
