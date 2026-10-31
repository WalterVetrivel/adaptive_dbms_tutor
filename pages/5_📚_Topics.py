"""Topic page: a short overview of one concept, where the student stands on it, and questions to practise it."""
import streamlit as st

from tutor import item_bank, misconception_tracker, onboarding, practice, topics, ui
from tutor.agents.overview import overview
from tutor.selector import QueueEntry

st.set_page_config(page_title="Topics · QueryMind", page_icon="📚", layout="wide")
conn, graph, notes, llm = ui.services()
sid = ui.sidebar()

cid = st.query_params.get("topic")
if cid not in graph.concepts:
    st.title("📚 Topics")
    st.caption("Pick a topic on the map to see an overview and practise it.")
    ui.concept_map(sid, key="topics_map")
    st.stop()

c = graph.concepts[cid]
states = topics.states(conn, graph, sid)
s = states[cid]

st.page_link("Home.py", label="Back to my dashboard", icon="⬅️")
st.title(f"📚 {c.name}")
plan_step = next((p for p in onboarding.plan(conn, sid) if p.concept_id == cid), None)
meta = [f"Unit {c.unit}: {graph.units[c.unit]}", f"Bloom {c.bloom}", topics.STATUS_LABEL[s.status]]
if c.demo_core:
    meta.append("core exam topic")
if plan_step:
    meta.append(f"📋 step {plan_step.position + 1} of your study plan")
st.caption(" · ".join(meta))

m1, m2, m3 = st.columns(3)
m1.metric("Your mastery", f"{s.mastery:.0%}" if s.mastery is not None else "–")
m2.metric("Questions answered", s.attempts)
m3.metric("Questions available", len(item_bank.items_for(conn, cid)))
if s.mastery is not None:
    st.progress(s.mastery, text="70% = mastered")

left, right = st.columns([3, 2], gap="large")

with right:
    st.markdown("#### Overview")
    with st.spinner("Writing an overview…"):
        ov = overview(llm, graph, notes, cid)
    st.markdown(ov.text)
    if ov.key_points:
        st.markdown("**Remember**")
        st.markdown("\n".join(f"- {p}" for p in ov.key_points))
    if ov.example:
        st.markdown("**Example**")
        st.code(ov.example, language="sql" if "SELECT" in ov.example.upper() else None)
    if ov.notes:
        with st.expander("📖 From your notes"):
            for ch in ov.notes:
                st.markdown(f"**{ch.source}, p.{ch.page} — {ch.heading}**")
                st.text(ch.text[:800])

    active = {r["misconception_id"]: r["status"] for r in misconception_tracker.for_student(conn, sid)}
    mcs = graph.misconceptions_for(cid)
    if mcs:
        st.markdown("#### Common mistakes")
        for m in mcs:
            flag = " · 🔴 **you've shown this one**" if active.get(m.id) == "active" else (
                " · 🟡 suspected" if active.get(m.id) == "suspected" else "")
            st.markdown(f"- _{m.belief}_{flag}  \n  {m.remediation}")

    def links(title: str, ids: list[str]):
        if not ids:
            return
        st.markdown(f"#### {title}")
        for other in ids:
            o = states[other]
            st.page_link("pages/5_📚_Topics.py", query_params={"topic": other},
                         label=f"{topics.STATUS_LABEL[o.status]} · {graph.concepts[other].name}"
                               + (f" (Unit {graph.concepts[other].unit})" if graph.concepts[other].unit != c.unit
                                  else ""))

    links("Builds on", graph.prereqs(cid))
    links("Leads to", graph.dependants(cid))

with left:
    st.markdown("#### Practise this topic")
    T = st.session_state.get("topic_q")
    if T is None or T["cid"] != cid or T.get("sid") != sid:
        T = st.session_state["topic_q"] = {"cid": cid, "sid": sid, "item_id": None, "outcome": None, "exp": None,
                                           "done": set(), "correct": 0, "how": ""}

    def load_next():
        with st.spinner("Finding a question…"):
            item, how = practice.next_item(conn, graph, notes, llm, sid, QueueEntry(cid, "topic"), T["done"])
        T["item_id"], T["how"], T["outcome"], T["exp"] = (item.id if item else None), how, None, None
        T["empty"] = item is None

    if T["item_id"] is None and not T.get("empty"):
        load_next()
    if T["done"]:
        st.caption(f"This visit: {T['correct']}/{len(T['done'])} correct")
    if T["item_id"] is None:
        if T["done"]:
            st.success("You've answered every question on this topic for now. Come back later for a review.")
        else:
            st.info("No questions for this topic yet." + (
                "" if llm else " Add a GROQ_API_KEY to generate verified questions on demand."))
    else:
        item = item_bank.get(conn, T["item_id"])
        if T["how"] == "generated":
            st.caption("✨ freshly generated for you")
        key = f"topic_{item.id}_{len(T['done'])}"
        if T["outcome"] is None:
            ans, why, submitted = ui.question_card(item, graph, key)
            if submitted:
                with st.spinner("Checking your answer and reasoning…"):
                    outcome, exp = ui.answer(item, sid, ans, why, "practice",
                                             st.session_state.get(f"{key}_elapsed_ms"))
                T["outcome"], T["exp"] = outcome, exp
                T["done"].add(item.id)
                T["correct"] += int(outcome.grade.correct)
                st.rerun()
            if st.button("Skip this question"):
                T["done"].add(item.id)
                load_next()
                st.rerun()
        else:
            st.markdown(f"#### {item.stem}")
            ui.feedback_card(item, T["outcome"], T["exp"])
            if st.button("Next question →", type="primary"):
                load_next()
                st.rerun()
