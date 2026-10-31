"""Student progress: mastery by concept, misconceptions and the evidence trail."""
import pandas as pd
import streamlit as st

from tutor import clock, learner_model, scheduler, ui

st.set_page_config(page_title="Progress · QueryMind", page_icon="📈", layout="wide")
conn, graph, notes, llm = ui.services()
sid = ui.sidebar()
st.title("📈 My progress")

now = clock.now(conn)
mastery = learner_model.get_all(conn, sid)
attempts = learner_model.attempts(conn, sid)
due = scheduler.next_due(conn, sid)

c1, c2, c3 = st.columns(3)
c1.metric("Concepts practised", sum(1 for v in attempts.values() if v))
c2.metric("Mastered (≥ 70%)", sum(1 for c, p in mastery.items() if p >= 0.7 and attempts.get(c)))
c3.metric("Reviews due now", len(scheduler.due(conn, sid, now)))

tab_map, tab_table, tab_mc, tab_log = st.tabs(["Concept map", "By concept", "Misconceptions", "Evidence log"])
with tab_map:
    core_only = st.toggle("Demo-core only", value=True)
    ui.mastery_map(graph, sid, core_only=core_only)
with tab_table:
    rows = []
    for c in graph.concepts.values():
        if c.id not in mastery:
            continue
        r = scheduler.retrievability(conn, sid, c.id, now)
        rows.append({"Unit": c.unit, "Concept": c.name, "Mastery": round(mastery[c.id] * 100),
                     "Attempts": attempts.get(c.id, 0), "Recall now": None if r is None else round(r * 100),
                     "Next review": (due.get(c.id) or "")[:10]})
    if rows:
        st.dataframe(pd.DataFrame(rows).sort_values(["Unit", "Mastery"]), hide_index=True, width="stretch",
                     column_config={"Mastery": st.column_config.ProgressColumn(min_value=0, max_value=100,
                                                                               format="%d%%"),
                                    "Recall now": st.column_config.NumberColumn(format="%d%%")})
    else:
        st.info("Take the diagnostic to see your mastery.")
with tab_mc:
    ui.active_misconceptions(sid)
with tab_log:
    st.caption("Every mastery change, with its cause. This is why the tutor thinks what it thinks.")
    ev = learner_model.events(conn, sid, limit=100)
    if ev:
        st.dataframe(pd.DataFrame([{"When": e["created_at"][:16].replace("T", " "),
                                    "Concept": graph.concepts[e["concept_id"]].name,
                                    "Before": f"{e['before']:.0%}", "After": f"{e['after']:.0%}",
                                    "Cause": e["cause"]} for e in ev]), hide_index=True, width="stretch")
