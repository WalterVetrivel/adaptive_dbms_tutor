"""QueryMind: adaptive DBMS exam-prep tutor (Streamlit entry point / student dashboard)."""
import streamlit as st

from tutor import bootstrap, config, item_bank, onboarding, students, topics, ui

st.set_page_config(page_title="QueryMind – DBMS Tutor", page_icon="🗄️", layout="wide")
conn, graph, notes, llm = ui.services()
sid = ui.sidebar()
if onboarding.needs_onboarding(conn, sid):     # first login: placement check before anything else
    st.switch_page(ui.GET_STARTED)

st.title("🗄️ QueryMind")
st.caption("Adaptive exam-prep tutor for BE23CS405 Database Management System. "
           "It doesn't just mark your SQL wrong: it works out *why* you wrote it.")

c1, c2, c3 = st.columns(3)
c1.page_link("pages/2_🏋️_Practice.py", label="**Today's practice**", icon="🏋️")
c2.page_link(ui.GET_STARTED, label="**My study plan**", icon="🧭")
c3.page_link("pages/3_📈_Progress.py", label="**My progress**", icon="📈")
st.divider()

student = students.get(conn, sid)
st.subheader(f"Hi {student['display_name'] if student else ''} 👋")
n = topics.counts(topics.states(conn, graph, sid))
m1, m2, m3, m4 = st.columns(4)
m1.metric("✅ Mastered", n["mastered"])
m2.metric("🟨 In progress", n["learning"])
m3.metric("🟥 Needs work", n["needs_work"])
m4.metric("⬜ Not started", n["not_started"], help=f"of {len(graph.concepts)} syllabus topics")

left, right = st.columns([2, 6], gap="medium")
with left:
    st.markdown("#### 📋 Study plan")
    ui.study_plan(sid, limit=6)
with right:
    st.markdown("#### 🗺️ Concept map")
    plan = onboarding.open_steps(conn, sid)
    ui.concept_map(sid, key="home_map", highlight=set(plan[:1]))

st.divider()
with st.expander("ℹ️ About this course"):
    a1, a2, a3, a4, a5 = st.columns(5)
    a1.metric("Concepts", len(graph.concepts))
    a2.metric("Demo-core concepts", len(graph.core_ids()))
    a3.metric("Misconceptions", len(graph.misconceptions))
    a4.metric("Verified questions", sum(sum(b.values()) for b in item_bank.counts(conn).values()))
    a5.metric("Notes chunks indexed", len(notes))
    st.page_link("pages/1_🩺_Diagnostic.py", label="Take the full adaptive diagnostic (12 questions)", icon="🩺")

if config.OFFLINE_MODE:
    st.info("Running in **offline mode** (no `GROQ_API_KEY`): misconception diagnosis uses rules only.")

with st.expander("🎬 Demo controls"):
    st.caption(f"Resets {bootstrap.DEMO_STUDENT[0]}'s progress (including the placement check) and the demo clock. "
               "The simulated class is kept.")
    if st.button("Reset demo"):
        bootstrap.reset_demo(conn)
        for k in [k for k in st.session_state if k.startswith(("diag", "practice", "onb", "topic"))]:
            del st.session_state[k]
        st.session_state["student_id"] = bootstrap.DEMO_STUDENT[1]
        st.switch_page(ui.GET_STARTED)
