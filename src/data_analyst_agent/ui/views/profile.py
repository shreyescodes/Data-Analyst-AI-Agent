from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from data_analyst_agent.profiling import build_profile_html, is_large
from data_analyst_agent.ui.components import require_data
from data_analyst_agent.ui.state import SessionState


def render(state: SessionState) -> None:
    st.header("Profile")
    df = require_data(state.active)
    if df is None:
        return

    st.write(
        "Generate a full profiling report (distributions, correlations, missing "
        "values, duplicates) with fg-data-profiling (formerly ydata-profiling)."
    )
    minimal = st.toggle(
        "Fast mode",
        value=is_large(df),
        help="Skips correlations and interactions. Enabled by default for large datasets.",
    )
    if st.button("Generate report", type="primary"):
        with st.spinner("Profiling... this can take a minute for wide datasets."):
            state.profile_html = build_profile_html(df, minimal=minimal)
            state.profile_revision = state.revision

    if state.profile_html is None or state.profile_revision != state.revision:
        return

    st.download_button(
        "Download HTML report",
        state.profile_html,
        file_name="profile_report.html",
        mime="text/html",
    )
    components.html(state.profile_html, height=900, scrolling=True)
