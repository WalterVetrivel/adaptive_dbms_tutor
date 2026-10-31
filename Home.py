"""QueryMind: adaptive DBMS exam-prep tutor (Streamlit entry point / home page)."""
import streamlit as st

from tutor import bootstrap, config, item_bank, ui
from tutor.viz import to_dot

st.set_page_config(page_title="QueryMind – DBMS Tutor", page_icon="🗄️", layout="wide")
conn, graph, notes, llm = ui.services()
sid = ui.sidebar()

st.title("🗄️ QueryMind")
st.caption("Adaptive exam-prep tutor for BE23CS405 Database Management System. "
           "It doesn't just mark your SQL wrong: it works out *why* you wrote it.")

c1, c2, c3 = st.columns(3)
c1.page_link("pages/1_🩺_Diagnostic.py", label="**Start with the diagnostic**", icon="🩺")
c2.page_link("pages/2_🏋️_Practice.py", label="**Today's practice**", icon="🏋️")
c3.page_link("pages/3_📈_Progress.py", label="**My progress**", icon="📈")
st.divider()

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Concepts", len(graph.concepts))
m2.metric("Demo-core concepts", len(graph.core_ids()))
m3.metric("Misconceptions", len(graph.misconceptions))
m4.metric("Verified questions", sum(sum(b.values()) for b in item_bank.counts(conn).values()))
m5.metric("Notes chunks indexed", len(notes))

if config.OFFLINE_MODE:
    st.info("Running in **offline mode** (no `GROQ_API_KEY`): misconception diagnosis uses rules only.")

with st.expander("🎬 Demo controls"):
    st.caption(f"Resets {bootstrap.DEMO_STUDENT[0]}'s progress and the demo clock. The simulated class is kept.")
    if st.button("Reset demo"):
        bootstrap.reset_demo(conn)
        for k in [k for k in st.session_state if k.startswith(("diag", "practice"))]:
            del st.session_state[k]
        st.session_state["student_id"] = bootstrap.DEMO_STUDENT[1]
        st.success("Demo reset.")

st.subheader("Course concept map")
col_a, col_b = st.columns([1, 3])
with col_a:
    units = st.multiselect("Units", options=list(graph.units), default=list(graph.units),
                           format_func=lambda u: f"Unit {u}: {graph.units[u]}")
    core_only = st.toggle("Demo-core only", value=True)
with col_b:
    st.graphviz_chart(to_dot(graph, units=units, core_only=core_only), width="stretch")
