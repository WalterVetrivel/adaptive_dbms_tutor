"""QueryMind: adaptive DBMS exam-prep tutor (Streamlit entry point)."""
import streamlit as st

from tutor import config
from tutor.db import init_db
from tutor.graph import get_graph
from tutor.retrieval import get_index
from tutor.viz import to_dot

st.set_page_config(page_title="QueryMind – DBMS Tutor", page_icon="🗄️", layout="wide")


@st.cache_resource
def _conn():
    return init_db()


conn = _conn()
graph = get_graph()

st.title("🗄️ QueryMind")
st.caption("Adaptive exam-prep tutor for BE23CS405 Database Management System")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Concepts", len(graph.concepts))
c2.metric("Demo-core concepts", len(graph.core_ids()))
c3.metric("Misconceptions", len(graph.misconceptions))
c4.metric("Notes chunks indexed", len(get_index()))

if config.OFFLINE_MODE:
    st.info("Running in **offline mode** (no `GROQ_API_KEY`): rule-based fallbacks only.")

st.subheader("Concept map")
col_a, col_b = st.columns([1, 3])
with col_a:
    units = st.multiselect("Units", options=list(graph.units), default=list(graph.units),
                           format_func=lambda u: f"Unit {u}: {graph.units[u]}")
    core_only = st.toggle("Demo-core only", value=True)
with col_b:
    st.graphviz_chart(to_dot(graph, units=units, core_only=core_only), width="stretch")

st.caption("Student and teacher pages arrive in later build phases.")
