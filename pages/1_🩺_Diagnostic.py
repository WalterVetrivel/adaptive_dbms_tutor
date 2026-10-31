"""Adaptive diagnostic test."""
import streamlit as st

from tutor import item_bank, learner_model, selector, ui

st.set_page_config(page_title="Diagnostic · QueryMind", page_icon="🩺", layout="wide")
conn, graph, notes, llm = ui.services()
sid = ui.sidebar()

st.title("🩺 Diagnostic test")
st.caption(f"About {selector.DIAGNOSTIC_LENGTH} questions across all 5 units. The test adapts: get something "
           "wrong and it checks the concepts that come before it. Always add a one-line *why*.")

d = st.session_state.setdefault("diag", {"asked": [], "last_wrong": None, "item_id": None, "outcome": None,
                                         "exp": None, "answer": "", "done": False, "results": []})


def next_item():
    concept = selector.next_diagnostic_concept(graph, conn, sid, d["asked"], d["last_wrong"])
    if concept is None or len(d["asked"]) >= selector.DIAGNOSTIC_LENGTH:
        d["done"], d["item_id"] = True, None
        return
    item = selector.pick_item(conn, sid, concept)
    d["asked"].append(concept)
    d["item_id"] = item.id if item else None
    d["outcome"] = d["exp"] = None
    if item is None:
        next_item()


left, right = st.columns([3, 2], gap="large")
with left:
    if not d["asked"] and not d["done"]:
        st.button("Start diagnostic", type="primary", on_click=next_item)
    elif d["done"]:
        st.success(f"Diagnostic complete: {sum(r for r in d['results'])}/{len(d['results'])} correct.")
        attempted = learner_model.get_all(conn, sid, attempted_only=True)
        weakest = sorted(attempted.items(), key=lambda kv: kv[1])[:3]
        st.markdown("#### 🎯 Your top focus areas")
        for cid, p in weakest:
            st.markdown(f"- **{graph.concepts[cid].name}** (Unit {graph.concepts[cid].unit}): {p:.0%} mastery")
        st.page_link("pages/2_🏋️_Practice.py", label="Go to today's practice →", icon="🏋️")
        if st.button("Retake diagnostic"):
            del st.session_state["diag"]
            st.rerun()
    elif d["item_id"]:
        item = item_bank.get(conn, d["item_id"])
        st.progress(len(d["asked"]) / selector.DIAGNOSTIC_LENGTH,
                    text=f"Question {len(d['asked'])} of {selector.DIAGNOSTIC_LENGTH}")
        key = f"diag_{item.id}"
        if d["outcome"] is None:
            ans, why, submitted = ui.question_card(item, graph, key)
            if submitted:
                with st.spinner("Checking your answer and reasoning…"):
                    outcome, exp = ui.answer(item, sid, ans, why, "diagnostic",
                                             st.session_state.get(f"{key}_elapsed_ms"))
                d["outcome"], d["exp"] = outcome, exp
                d["results"].append(outcome.grade.correct)
                d["last_wrong"] = None if outcome.grade.correct else item.concept_id
                st.rerun()
        else:
            st.markdown(f"#### {item.stem}")
            ui.feedback_card(item, d["outcome"], d["exp"])
            st.button("Next question →", type="primary", on_click=next_item)

with right:
    st.markdown("#### Your concept map")
    ui.mastery_map(graph, sid, highlight={d["asked"][-1]} if d["asked"] and not d["done"] else None, compact=True)
