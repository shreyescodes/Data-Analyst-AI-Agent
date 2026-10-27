"""Streamlit application shell: page setup, sidebar and tab routing."""

from __future__ import annotations

import streamlit as st

from data_analyst_agent.config import Settings
from data_analyst_agent.exceptions import ConfigurationError
from data_analyst_agent.ui.resources import get_assistant, get_settings, get_version_store
from data_analyst_agent.ui.state import SessionState, get_state, reset_state
from data_analyst_agent.ui.views import clean, ingest, profile, query, settings, visualize

TITLE = "Data Analyst AI Agent"


def main() -> None:
    st.set_page_config(page_title=TITLE, page_icon="📊", layout="wide")

    try:
        app_settings = get_settings()
    except ConfigurationError as exc:
        st.error(f"Invalid configuration: {exc}")
        st.stop()

    assistant = get_assistant()
    state = get_state()

    st.title(TITLE)
    st.caption("Load a dataset, clean it, ask questions in plain English, and explore it.")

    tabs = st.tabs(["Load data", "Clean", "Ask & query", "Visualise", "Profile", "Settings"])
    with tabs[0]:
        ingest.render(state, app_settings)
    with tabs[1]:
        clean.render(state, get_version_store())
    with tabs[2]:
        query.render(state, app_settings, assistant)
    with tabs[3]:
        visualize.render(state)
    with tabs[4]:
        profile.render(state)
    with tabs[5]:
        settings.render(app_settings, assistant)

    # Rendered last so it reflects any state changed by the tabs in this run.
    _sidebar(state, app_settings)


def _sidebar(state: SessionState, app_settings: Settings) -> None:
    with st.sidebar:
        st.subheader("Dataset")
        if state.active is None:
            st.caption("No data loaded.")
        else:
            rows, cols = state.active.shape
            st.markdown(f"**{state.source_label}**  \n{rows:,} rows x {cols} columns")
            st.caption("Cleaned" if state.is_cleaned else "Raw (not cleaned yet)")
            if st.button("Clear dataset"):
                reset_state()
                st.rerun()

        st.subheader("AI")
        if app_settings.llm_enabled:
            st.caption(f"LLM: {app_settings.llm_model}")
        else:
            st.caption("Rule-based mode (no LLM key set)")
