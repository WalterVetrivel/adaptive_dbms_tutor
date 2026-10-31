"""Today's practice: spaced-repetition reviews + weakest concepts + active misconceptions."""
import streamlit as st

from tutor import clock, item_bank, practice, scheduler, selector, ui

st.set_page_config(page_title="Practice · QueryMind", page_icon="🏋️", layout="wide")
conn, graph, notes, llm = ui.services()
sid = ui.sidebar()
now = clock.now(conn)

st.title("🏋️ Today's practice")
REASON = {"review due": "🔁 Review due", "weak concept": "🎯 Weak concept",
          "misconception": "🧠 Fixing a misconception", "new": "✨ New concept"}

c1, c2, c3, c4 = st.columns(4)
c1.metric("Reviews due", len(scheduler.due(conn, sid, now)))
c2.metric("Answered today", practice.answered_today(conn, sid, now))
c3.metric("Streak", f"{practice.streak(conn, sid, now.date())} 🔥")
c4.metric("Active misconceptions", sum(1 for r in ui.misconception_tracker.for_student(conn, sid, ("active",))))

if "practice" not in st.session_state:
    queue = selector.practice_queue(conn, graph, sid, now, size=10)
    st.session_state["practice"] = {"queue": queue, "pos": 0, "item_id": None, "how": "", "outcome": None,
                                    "exp": None, "done_ids": set(), "correct": 0}
P = st.session_state["practice"]


def load_current():
    while P["pos"] < len(P["queue"]):
        entry = P["queue"][P["pos"]]
        with st.spinner("Preparing your next question…"):
            item, how = practice.next_item(conn, graph, notes, llm, sid, entry, P["done_ids"])
        if item:
            P["item_id"], P["how"], P["outcome"], P["exp"] = item.id, how, None, None
            return
        P["pos"] += 1
    P["item_id"] = None


def advance():
    P["pos"] += 1
    P["item_id"] = None


if P["item_id"] is None and P["pos"] < len(P["queue"]):
    load_current()

left, right = st.columns([3, 2], gap="large")
with left:
    if not P["queue"]:
        st.info("Nothing queued. Take the diagnostic first.")
        st.page_link("pages/1_🩺_Diagnostic.py", label="Start the diagnostic", icon="🩺")
    elif P["item_id"] is None:
        st.success(f"🎉 Session complete: {P['correct']}/{len(P['done_ids'])} correct. "
                   "Come back tomorrow for your reviews (or skip ahead with the demo clock).")
        if st.button("Start another session"):
            del st.session_state["practice"]
            st.rerun()
    else:
        entry = P["queue"][P["pos"]]
        item = item_bank.get(conn, P["item_id"])
        st.progress(P["pos"] / len(P["queue"]), text=f"Question {P['pos'] + 1} of {len(P['queue'])}")
        label = REASON[entry.reason]
        if entry.misconception:
            label += f": _{graph.misconceptions[entry.misconception].belief}_"
        if P["how"] == "generated":
            label += " · ✨ freshly generated for you"
        st.markdown(label)
        key = f"practice_{item.id}_{P['pos']}"
        if P["outcome"] is None:
            ans, why, submitted = ui.question_card(item, graph, key)
            if submitted:
                with st.spinner("Checking your answer and reasoning…"):
                    outcome, exp = ui.answer(item, sid, ans, why, "practice",
                                             st.session_state.get(f"{key}_elapsed_ms"))
                P["outcome"], P["exp"] = outcome, exp
                P["done_ids"].add(item.id)
                P["correct"] += int(outcome.grade.correct)
                st.rerun()
            st.button("Skip", on_click=advance)
        else:
            st.markdown(f"#### {item.stem}")
            ui.feedback_card(item, P["outcome"], P["exp"])
            st.button("Next →", type="primary", on_click=advance)

with right:
    st.markdown("#### Up next")
    for i, e in enumerate(P["queue"]):
        mark = "▶️" if i == P["pos"] else ("✔️" if i < P["pos"] else "·")
        st.markdown(f"{mark} {REASON[e.reason]}: **{graph.concepts[e.concept_id].name}**")
    st.divider()
    st.markdown("#### Misconceptions")
    ui.active_misconceptions(sid)
