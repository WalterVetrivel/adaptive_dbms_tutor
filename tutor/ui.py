"""Shared Streamlit building blocks for the student and teacher pages."""
from __future__ import annotations

import time

import streamlit as st

from . import (calibration, clock, config, item_bank, learner_model, misconception_tracker, onboarding, sql_sandbox,
               students)
from .agents.analyst import make_analyst
from .agents.explainer import Explanation, explain
from .db import init_db
from .graph import ConceptGraph, get_graph
from .llm import LLM
from .orchestrator import AnswerOutcome, submit_answer
from .retrieval import NotesIndex, get_index
from .schemas import Item
from .viz import to_dot

from .bootstrap import DEMO_STUDENT, ensure_all


GET_STARTED = "pages/0_🧭_Get_started.py"


@st.cache_resource(show_spinner="Setting up QueryMind (first run builds the demo class)…")
def services():
    conn = init_db()
    graph = get_graph()
    ensure_all(conn, graph)
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
            for k in [k for k in st.session_state if k.startswith(("diag", "practice", "onb"))]:
                del st.session_state[k]
        with st.popover("➕ New student"):
            name = st.text_input("Name")
            if st.button("Create", disabled=not name.strip()):
                st.session_state["student_id"] = students.create(conn, name.strip())
                for k in [k for k in st.session_state if k.startswith(("diag", "practice", "onb"))]:
                    del st.session_state[k]
                st.switch_page(GET_STARTED)
        st.divider()
        off = clock.offset_days(conn)
        st.caption(f"🕒 {clock.now(conn):%d %b %Y}" + (f" (demo clock +{off:g} days)" if off else ""))
        with st.popover("⏩ Demo clock"):
            st.caption("Skip ahead to show spaced repetition.")
            c1, c2, c3 = st.columns(3)
            for col, days in zip((c1, c2, c3), (1, 3, 7)):
                if col.button(f"+{days}d", key=f"adv{days}"):
                    clock.advance(conn, days)
                    st.session_state.pop("practice", None)
                    st.rerun()
            if off and st.button("Reset to today"):
                clock.reset(conn)
                st.session_state.pop("practice", None)
                st.rerun()
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
    conn = services()[0]
    elo = conn.execute("SELECT elo, n_responses FROM items WHERE id=?", (item.id,)).fetchone()
    sid = st.session_state.get("student_id", "")
    p = calibration.expected(calibration.student_elo(conn, sid, item.concept_id), elo["elo"]) if elo else None
    badges = [f"Unit {c.unit} · **{c.name}**", item.type.upper(), f"{item.difficulty_band}"]
    if elo:
        badges.append(f"difficulty {elo['elo']:.0f} Elo ({elo['n_responses']} responses)")
    if p is not None:
        badges.append(f"predicted success {p:.0%}")
    if item.verified:
        badges.append("✅ verified" + (" by execution" if item.type == "sql" else
                                       " by algorithm" if item.type in ("fd", "schedule") else ""))
    if item.source == "generated":
        badges.append("✨ AI-generated")
    st.caption(" · ".join(badges), help=item.verification_note or None)
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
           elapsed_ms: int | None, explain_mistakes: bool = True) -> tuple[AnswerOutcome, Explanation | None]:
    conn, graph, notes, llm = services()
    analyst = make_analyst(llm, graph) if llm else None
    errors: list[Exception] = []
    outcome = submit_answer(conn, graph, student_id, item, answer_text, reasoning, mode, elapsed_ms,
                            analyst=analyst, on_error=errors.append)
    if errors:
        st.toast("Groq unavailable, used rule-based diagnosis", icon="⚠️")
    exp = explain(llm, graph, notes, item, answer_text, reasoning, outcome) if explain_mistakes and (
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


def study_plan(student_id: str, limit: int | None = None):
    """The student's study plan as a checklist, with live mastery. Shows a call to action if there is none."""
    conn, graph, _, _ = services()
    steps = onboarding.plan(conn, student_id)
    if not steps:
        if onboarding.status(conn, student_id) == "completed":
            st.caption("Nothing to fix: you aced the placement check. Practice keeps you sharp.")
        else:
            st.page_link(GET_STARTED, label="Take the 10-question placement check to get your study plan",
                         icon="🧭")
        return
    done = sum(s.done for s in steps)
    st.progress(done / len(steps), text=f"{done} of {len(steps)} topics mastered")
    nxt = next((s for s in steps if not s.done), None)
    for s in steps[:limit]:
        c = graph.concepts[s.concept_id]
        mark = "✅" if s.done else ("▶️" if s is nxt else "⬜")
        level = f"{s.mastery:.0%}" if s.attempted else "not practised yet"
        st.markdown(f"{mark} **{c.name}** · Unit {c.unit} · {level}  \n"
                    f"<span style='opacity:0.7;font-size:0.9em'>{s.reason}</span>", unsafe_allow_html=True)
    if limit and len(steps) > limit:
        st.caption(f"…and {len(steps) - limit} more")


TOPIC_PAGE = "pages/5_📚_Topics.py"


def _on_map_click(key: str):
    ev = st.session_state.get(key) or {}
    try:
        pts = ev["selection"]["points"]
    except (KeyError, TypeError):
        pts = []
    for p in pts:
        cid = p.get("customdata")
        if isinstance(cid, list):
            cid = cid[0]
        if cid:
            st.session_state["goto_topic"] = cid
            return


def concept_map(student_id: str, key: str = "map", highlight: set[str] | None = None):
    """Clickable, mastery-coloured concept map, one unit at a time. Clicking a topic opens its page."""
    from . import topics

    conn, graph, _, _ = services()
    states = topics.states(conn, graph, student_id)
    default = st.session_state.get(f"{key}_unit") or next(
        (graph.concepts[c].unit for c in (highlight or [])), 1)
    unit = st.segmented_control("Unit", options=list(graph.units), default=default, key=f"{key}_unit",
                                format_func=lambda u: f"Unit {u}", label_visibility="collapsed") or default
    done = sum(states[c.id].status == "mastered" for c in graph.by_unit(unit))
    st.caption(f"**Unit {unit}: {graph.units[unit]}** · {done}/{len(graph.by_unit(unit))} topics mastered · "
               "click a topic to open it")
    nonce = st.session_state.setdefault(f"{key}_nonce", 0)
    chart_key = f"{key}_chart_{unit}_{nonce}"
    st.plotly_chart(topics.map_figure(graph, unit, states, highlight), key=chart_key,
                    on_select=lambda: _on_map_click(chart_key), selection_mode="points",
                    config={"displayModeBar": False})
    st.caption("🟥 < 40%  🟨 40–70%  🟩 ≥ 70%  ⬜ not assessed yet · dark border = core exam topic")
    if cid := st.session_state.pop("goto_topic", None):
        st.session_state[f"{key}_nonce"] = nonce + 1     # fresh chart (no lingering selection) on return
        st.switch_page(TOPIC_PAGE, query_params={"topic": cid})
    with st.expander(f"All Unit {unit} topics as a list"):
        for c in graph.by_unit(unit):
            s = states[c.id]
            pct = f" · {s.mastery:.0%}" if s.mastery is not None else ""
            st.page_link(TOPIC_PAGE, label=f"{topics.STATUS_LABEL[s.status]} · {c.name}{pct}",
                         query_params={"topic": c.id})
