"""Today's practice (filled in by Phase 5)."""
import streamlit as st

from tutor import ui

st.set_page_config(page_title="Practice · QueryMind", page_icon="🏋️", layout="wide")
ui.services()
ui.sidebar()
st.title("🏋️ Today's practice")
st.info("The spaced-repetition practice queue arrives in Phase 5.")
