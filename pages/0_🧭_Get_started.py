"""First-login placement check: two quick questions per unit, then a personal study plan."""
import streamlit as st

from tutor import item_bank, onboarding, ui

st.set_page_config(page_title="Get started · QueryMind", page_icon="🧭", layout="wide")
conn, graph, notes, llm = ui.services()
sid = ui.sidebar()

st.title("🧭 Get started")
n_units = len(graph.units)
per_unit = onboarding.QUESTIONS_PER_UNIT

O = st.session_state.get("onb")
if O is not None and O.get("sid") != sid:
    O = st.session_state["onb"] = None


def start():
    items = onboarding.choose_items(conn, graph, sid, attempt=onboarding.attempts_so_far(conn, sid))
    st.session_state["onb"] = {"sid": sid, "item_ids": [i.id for i in items], "pos": 0, "results": [],
                               "plan": None}


def record(item, correct: bool):
    O["results"].append((item.concept_id, correct))
    O["pos"] += 1
    if O["pos"] >= len(O["item_ids"]):
        O["plan"] = onboarding.complete(conn, graph, sid, O["results"])


def dont_know(item):
    onboarding.record_dont_know(conn, graph, sid, item)
    record(item, False)


def show_results():
    scores = onboarding.unit_scores(conn, sid)
    if scores:
        st.markdown("#### Where you stand")
        cols = st.columns(len(graph.units))
        for col, (u, title) in zip(cols, graph.units.items()):
            ok, asked = scores.get(u, (0, 0))
            label = "💪 Strong" if asked and ok == asked else ("🙂 Getting there" if ok else "🎯 Focus here")
            col.metric(f"Unit {u}", f"{ok}/{asked}" if asked else "–", help=title)
            col.caption(label)
    st.markdown("#### 📋 Your study plan")
    st.caption("Work through these in order: foundations come first. Each topic ticks off once you reach 70% "
               "mastery. Today's practice pulls from this plan automatically.")
    ui.study_plan(sid)
    c1, c2, c3 = st.columns(3)
    c1.page_link("pages/2_🏋️_Practice.py", label="**Start today's practice →**", icon="🏋️")
    c2.page_link("Home.py", label="Explore the concept map", icon="🗺️")
    if c3.button("Retake the placement check"):
        start()
        st.rerun()


left, right = st.columns([3, 2], gap="large")
with left:
    if O is None:
        state = onboarding.status(conn, sid)
        if state == "completed":
            show_results()
        else:
            st.markdown(f"Welcome! Before you start, answer **{per_unit * n_units} quick questions** "
                        f"({per_unit} from each of the {n_units} units). It takes about 5 minutes and tells the "
                        "tutor where you stand, so it can build a study plan around what *you* need.")
            st.caption("Not sure? Press **I don't know** rather than guessing: it makes your plan more accurate. "
                       "The *why* box is optional here.")
            b1, b2 = st.columns([1, 4])
            b1.button("Start", type="primary", on_click=start)
            if state is None and b2.button("Skip for now"):
                onboarding.skip(conn, sid)
                st.switch_page("Home.py")
    elif O["plan"] is not None:
        right_n = sum(ok for _, ok in O["results"])
        st.success(f"Placement check complete: {right_n}/{len(O['results'])} correct. Here's your plan.")
        show_results()
    else:
        item = item_bank.get(conn, O["item_ids"][O["pos"]])
        st.progress(O["pos"] / len(O["item_ids"]),
                    text=f"Question {O['pos'] + 1} of {len(O['item_ids'])} · Unit {graph.concepts[item.concept_id].unit}")
        key = f"onb_{item.id}_{O['pos']}"
        ans, why, submitted = ui.question_card(item, graph, key)
        if submitted:
            with st.spinner("Recording your answer…"):
                outcome, _ = ui.answer(item, sid, ans, why, "onboarding",
                                       st.session_state.get(f"{key}_elapsed_ms"), explain_mistakes=False)
            st.toast("✅ Correct" if outcome.grade.correct else "Answer recorded")
            record(item, outcome.grade.correct)
            st.rerun()
        st.button("I don't know", on_click=dont_know, args=(item,))

with right:
    st.markdown("#### Your concept map")
    if O is not None and O["plan"] is None:
        current = {item_bank.get(conn, O["item_ids"][O["pos"]]).concept_id}
        ui.mastery_map(graph, sid, highlight=current, compact=True)
    else:
        ui.mastery_map(graph, sid)
        st.page_link("Home.py", label="Open the interactive map on your dashboard: click any topic to study it",
                     icon="🗺️")
