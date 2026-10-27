from __future__ import annotations

import streamlit as st

from data_analyst_agent.charts import (
    correlation_heatmap,
    distribution_plot,
    render_chart,
    suggest_chart,
)
from data_analyst_agent.exceptions import ChartError
from data_analyst_agent.schema import Schema
from data_analyst_agent.ui.components import require_data
from data_analyst_agent.ui.state import SessionState


def render(state: SessionState) -> None:
    st.header("Visualise")
    df = require_data(state.active)
    if df is None:
        return

    with st.form("chart_request"):
        request = st.text_input(
            "Describe a chart",
            placeholder="e.g. revenue over time, units vs unit price, share of orders by region",
        )
        submitted = st.form_submit_button("Create chart", type="primary")
    if submitted:
        try:
            state.chart = suggest_chart(request, df)
        except ChartError as exc:
            st.error(str(exc))

    if state.chart is not None:
        try:
            figure = render_chart(df, state.chart)
        except ChartError as exc:
            st.error(str(exc))
        else:
            st.plotly_chart(figure, width="stretch")
            st.caption(state.chart.rationale)

    st.divider()
    st.subheader("Quick look")
    numeric = Schema.from_frame(df).numeric
    if not numeric:
        st.caption("The dataset has no numeric columns to summarise.")
        return

    left, right = st.columns(2)
    with left:
        if len(numeric) >= 2:
            st.plotly_chart(correlation_heatmap(df), width="stretch")
        else:
            st.caption("A correlation matrix needs at least two numeric columns.")
    with right:
        column = st.selectbox("Column", numeric)
        st.plotly_chart(distribution_plot(df, column), width="stretch")
