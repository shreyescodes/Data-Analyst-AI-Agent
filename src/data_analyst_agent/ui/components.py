"""Small rendering helpers reused across tabs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from data_analyst_agent.storage import QueryResult

_PREVIEW_ROWS = 100


def format_bytes(n_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


def dataset_overview(df: pd.DataFrame) -> None:
    rows, cols, memory = st.columns(3)
    rows.metric("Rows", f"{len(df):,}")
    cols.metric("Columns", df.shape[1])
    memory.metric("Memory", format_bytes(float(df.memory_usage(deep=True).sum())))
    st.dataframe(df.head(_PREVIEW_ROWS), width="stretch")
    if len(df) > _PREVIEW_ROWS:
        st.caption(f"Showing the first {_PREVIEW_ROWS} of {len(df):,} rows.")


def query_result(result: QueryResult, *, key: str) -> None:
    st.dataframe(result.frame, width="stretch")
    if result.truncated:
        st.warning(
            f"Showing the first {len(result.frame):,} rows. "
            "Add a LIMIT or aggregate to see the full result."
        )
    st.download_button(
        "Download result as CSV",
        result.frame.to_csv(index=False),
        file_name="query_result.csv",
        mime="text/csv",
        key=key,
    )


def require_data(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None:
        st.info("Load a dataset in the **Load data** tab first.")
    return df
