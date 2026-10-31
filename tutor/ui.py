"""Shared Streamlit building blocks for the student and teacher pages."""
from __future__ import annotations

import time

import streamlit as st

from . import clock, config, item_bank, learner_model, misconception_tracker, sql_sandbox, students
from .agents.analyst import make_analyst
from .agents.explainer import Explanation, explain
from .db import init_db
from .graph import ConceptGraph, get_graph
from .llm import LLM
from .orchestrator import AnswerOutcome, submit_answer
from .retrieval import NotesIndex, get_index
from .schemas import Item
from .viz import to_dot

DEMO_STUDENT = ("Riya", "riya")


@st.cache_resource
def services():
    conn = init_db()
    graph = get_graph()
    if not item_bank.counts(conn):
        item_bank.load_all(conn, graph, [p for p in (config.CONTENT_DIR / "seed_items.yaml", config.ITEMS_PATH)
                                         if p.exists()])
    students.create(conn, DEMO_STUDENT[0], student_id=DEMO_STUDENT[1])
    llm = None if config.OFFLINE_MODE else LLM(conn)
    return conn, graph, get_index(), llm


def sidebar() -> str:
    """Student picker + status. Returns the selected student id."""
    conn, graph, notes, llm = services()
    with st.sidebar:
        st.markdown("### 👤 Student")
        rows = students.all_students(conn, include_simulated=False)
        ids = [r["id"] for r in rows]
        names = {r["id"]: r["display_name"] for r in rows}
        current = st.session_state.get("student_id", DEMO_STUDENT[1])
        sid = st.selectbox("Signed in as", ids, index=ids.index(current) if current in ids else 0,
                           format_func=names.get, label_visibility="collapsed")
        if sid != st.session_state.get("student_id"):
            st.session_state["student_id"] = sid
            for k in [k for k in st.session_state if k.startswith(("diag", "practice"))]:
                del st.session_state[k]
        with st.popover("➕ New student"):
            name = st.text_input("Name")
            if st.button("Create", disabled=not name.strip()):
                st.session_state["student_id"] = students.create(conn, name.strip())
                st.rerun()
        st.divider()
        off = clock.offset_days(conn)
        st.caption(f"🕒 {clock.now(conn):%d %b %Y}" + (f" (demo clock +{off:g} days)" if off else ""))
        if config.OFFLINE_MODE:
            st.caption("⚙️ Offline mode: rule-based diagnosis")
        else:
            u = llm.usage_summary()
            st.caption(f"⚙️ Groq: {u['calls']} calls ({u['cached']} cached)")
    return st.session_state.setdefault("student_id", sid)


def mastery_map(graph: ConceptGraph, student_id: str, core_only: bool = True, highlight: set[str] | None = None,
                compact: bool = False):
    """compact=True shows only the unit(s) of the highlighted concept(s), top-to-bottom, for side panels."""
    conn = services()[0]
    m = learner_model.get_all(conn, student_id)
    units = sorted({graph.concepts[c].unit for c in highlight}) if compact and highlight else None
    if units:
        st.caption(" · ".join(f"Unit {u}: {graph.units[u]}" for u in units))
    st.graphviz_chart(to_dot(graph, m, core_only=core_only, highlight=highlight, units=units,
                             rankdir="TB" if compact else "LR"), width="stretch")
    st.caption("🟥 < 40%  🟨 40–70%  🟩 ≥ 70%  ⬜ not assessed yet · bold border = demo-core")


def _schema_help():
    with st.expander("📋 Practice database schema"):
        st.code(sql_sandbox.schema_text(), language="sql")


def question_card(item: Item, graph: ConceptGraph, key: str) -> tuple[str, str, bool]:
    """Render a question. Returns (answer, reasoning, submitted)."""
    c = graph.concepts[item.concept_id]
    st.caption(f"Unit {c.unit} · **{c.name}** · {item.difficulty_band} · {item.type.upper()}"
               + (" · ✅ verified" if item.verified else ""))
    st.markdown(f"#### {item.stem}")
    started = st.session_state.setdefault(f"{key}_started", time.time())
    if item.type == "sql":
        _schema_help()
    with st.form(key=f"form_{key}"):
        if item.type == "mcq":
            choice = st.radio("Your answer", [f"{l}. {o}" for l, o in zip("ABCD", item.options or [])],
                              index=None, key=f"{key}_ans")
            answer = (choice or "")[:1]
        elif item.type == "sql":
            answer = st.text_area("Your SQL (SQLite)", height=120, key=f"{key}_ans",
                                  placeholder="SELECT ...")
        else:
            hint = {"fd": "e.g. AB, BD   ·   ABCDE   ·   3NF   ·   yes/no",
                    "schedule": "yes / no, or a serial order like T1 -> T2"}[item.type]
            answer = st.text_input("Your answer", key=f"{key}_ans", placeholder=hint)
        reasoning = st.text_input("Why? (one line — this is how the tutor understands your thinking)",
                                  key=f"{key}_why")
        cols = st.columns([1, 1, 4])
        submitted = cols[0].form_submit_button("Submit", type="primary")
        preview = item.type == "sql" and cols[1].form_submit_button("▶ Run")
    if preview and answer.strip():
        r = sql_sandbox.run_query(answer)
        if r.ok:
            st.dataframe([dict(zip(r.columns, row)) for row in r.rows[:50]], width="stretch")
        else:
            st.error(r.error)
    st.session_state[f"{key}_elapsed_ms"] = int((time.time() - started) * 1000)
    if submitted and not answer.strip():
        st.warning("Enter an answer first.")
        submitted = False
    return answer, reasoning, submitted


def answer(item: Item, student_id: str, answer_text: str, reasoning: str, mode: str,
           elapsed_ms: int | None) -> tuple[AnswerOutcome, Explanation]:
    conn, graph, notes, llm = services()
    analyst = make_analyst(llm, graph) if llm else None
    errors: list[Exception] = []
    outcome = submit_answer(conn, graph, student_id, item, answer_text, reasoning, mode, elapsed_ms,
                            analyst=analyst, on_error=errors.append)
    if errors:
        st.toast("Groq unavailable, used rule-based diagnosis", icon="⚠️")
    exp = explain(llm, graph, notes, item, answer_text, reasoning, outcome) if (
        not outcome.grade.correct or outcome.diagnosis.flawed_reasoning) else None
    return outcome, exp


def feedback_card(item: Item, outcome: AnswerOutcome, exp: Explanation | None):
    conn, graph, _, _ = services()
    g = outcome.grade
    if g.correct and not outcome.diagnosis.flawed_reasoning:
        st.success(f"✅ Correct! {'' if item.type == 'mcq' else g.feedback}")
    elif g.correct:
        st.warning("✅ Right answer, but your reasoning suggests a misunderstanding.")
    else:
        st.error(f"❌ {g.feedback}")
        if item.type == "sql":
            with st.expander("Expected query"):
                st.code(item.reference_sql, language="sql")
    for mc, conf in outcome.diagnosis.misconceptions:
        m = graph.misconceptions[mc]
        badge = "🆕 now active" if mc in outcome.newly_active else ""
        st.markdown(f"**🧠 Misconception detected** `{mc}` ({conf:.0%} confidence, {outcome.diagnosis.source}) "
                    f"{badge}  \n_{m.belief}_")
    if outcome.diagnosis.rationale and outcome.diagnosis.source == "llm":
        st.caption(f"Analyst: {outcome.diagnosis.rationale}")
    for mc in outcome.resolved:
        st.success(f"🎉 Misconception resolved: {graph.misconceptions[mc].belief}")
    if exp:
        st.info(exp.text)
        if exp.contrast_question:
            st.markdown(f"**Try this:** {exp.contrast_question}")
        if exp.notes:
            with st.expander("📖 From your notes"):
                for ch in exp.notes:
                    st.markdown(f"**{ch.source}, p.{ch.page} — {ch.heading}**")
                    st.text(ch.text[:800])
    elif item.solution and g.correct:
        st.caption(item.solution)
    m = outcome.mastery
    cols = st.columns(1 + min(3, len(m.propagated)))
    cols[0].metric(graph.concepts[m.main.concept_id].name, f"{m.main.after:.0%}",
                   f"{(m.main.after - m.main.before) * 100:+.0f} pts")
    for col, ch in zip(cols[1:], m.propagated[:3]):
        col.metric(graph.concepts[ch.concept_id].name, f"{ch.after:.0%}",
                   f"{(ch.after - ch.before) * 100:+.0f} pts", help=ch.cause)
    st.caption(f"Next review of this concept: {outcome.next_review[:10]}")


def active_misconceptions(student_id: str):
    conn, graph, _, _ = services()
    rows = misconception_tracker.for_student(conn, student_id)
    if not rows:
        st.caption("No misconceptions detected yet.")
    for r in rows:
        icon = "🔴" if r["status"] == "active" else "🟡"
        st.markdown(f"{icon} **{graph.misconceptions[r['misconception_id']].belief}** "
                    f"· {r['status']} · seen {r['occurrences']}×")
