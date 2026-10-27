from __future__ import annotations

import pandas as pd
import streamlit as st

from data_analyst_agent.cleaning import (
    CleaningOptions,
    CleaningReport,
    MissingValueStrategy,
    assess_quality,
    clean,
)
from data_analyst_agent.exceptions import VersioningError
from data_analyst_agent.ui.components import require_data
from data_analyst_agent.ui.state import SessionState
from data_analyst_agent.versioning import VersionStore

_STRATEGY_LABELS = {
    MissingValueStrategy.DROP_ROWS: "Drop rows with missing values",
    MissingValueStrategy.MEAN: "Fill numeric columns with the mean",
    MissingValueStrategy.MEDIAN: "Fill numeric columns with the median",
    MissingValueStrategy.MODE: "Fill every column with its most common value",
    MissingValueStrategy.FORWARD_FILL: "Fill with the previous row's value",
    MissingValueStrategy.BACKWARD_FILL: "Fill with the next row's value",
}


def render(state: SessionState, versions: VersionStore) -> None:
    st.header("Clean")
    raw = require_data(state.raw)
    if raw is None:
        return

    _quality_summary(raw)
    options = _options_form()
    if options is not None:
        with st.spinner("Cleaning..."):
            cleaned, report = clean(raw, options)
        state.set_cleaned(cleaned, report)

    if state.cleaned is not None:
        _results(raw, state.cleaned, state.cleaning_report)

    st.divider()
    _versions(state, versions)


def _quality_summary(df: pd.DataFrame) -> None:
    quality = assess_quality(df)
    cols = st.columns(4)
    cols[0].metric("Rows", f"{quality.n_rows:,}")
    cols[1].metric(
        "Missing or blank cells",
        f"{quality.missing_cells:,} ({quality.missing_ratio:.1%})",
    )
    cols[2].metric("Duplicate rows", f"{quality.duplicate_rows:,}")
    cols[3].metric("Numbers stored as text", len(quality.numeric_text_columns))


def _options_form() -> CleaningOptions | None:
    with st.form("cleaning_options"):
        left, right = st.columns(2)
        normalise = left.checkbox("Trim and normalise text", value=True)
        dates = left.checkbox("Parse date columns", value=True)
        numeric = left.checkbox("Convert numbers stored as text", value=True)
        duplicates = right.checkbox("Remove duplicate rows", value=True)
        missing = right.checkbox("Handle missing values", value=True)
        outliers = right.checkbox(
            "Remove outliers (1.5 x IQR)",
            value=False,
            help="Drops rows with a value outside Q1 - 1.5 IQR or Q3 + 1.5 IQR "
            "in any numeric column.",
        )
        strategy = st.selectbox(
            "Missing value strategy",
            list(MissingValueStrategy),
            format_func=_STRATEGY_LABELS.__getitem__,
        )
        if not st.form_submit_button("Run cleaning", type="primary"):
            return None
    return CleaningOptions(
        normalise_text=normalise,
        parse_dates=dates,
        convert_numeric_text=numeric,
        remove_duplicates=duplicates,
        handle_missing=missing,
        missing_strategy=strategy or MissingValueStrategy.DROP_ROWS,
        remove_outliers=outliers,
    )


def _results(raw: pd.DataFrame, cleaned: pd.DataFrame, report: CleaningReport | None) -> None:
    st.subheader("Result")
    before, after, removed = st.columns(3)
    before.metric("Rows before", f"{len(raw):,}")
    after.metric("Rows after", f"{len(cleaned):,}")
    removed.metric("Rows removed", f"{len(raw) - len(cleaned):,}")

    if report is not None:
        st.dataframe(
            pd.DataFrame(
                {"Step": s.name, "Result": s.detail, "Rows removed": s.rows_removed}
                for s in report.steps
            ),
            hide_index=True,
            width="stretch",
        )

    st.dataframe(cleaned.head(100), width="stretch")
    st.download_button(
        "Download cleaned CSV",
        cleaned.to_csv(index=False),
        file_name="cleaned_data.csv",
        mime="text/csv",
    )


def _versions(state: SessionState, versions: VersionStore) -> None:
    st.subheader("Snapshots")
    st.caption(
        "Save the current dataset as an immutable, checksummed snapshot and restore it later."
    )

    active = state.active
    if active is not None:
        with st.form("save_version", clear_on_submit=True):
            message = st.text_input("Description", placeholder="e.g. Dropped test rows")
            if st.form_submit_button("Save snapshot"):
                try:
                    version = versions.save(active, message)
                except VersioningError as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Saved snapshot {version.version_id}.")

    history = versions.history()
    if not history:
        st.caption("No snapshots yet.")
        return

    for version in history:
        info, action = st.columns([5, 1])
        info.markdown(
            f"**{version.version_id}**  \n"
            f"{version.created_at:%Y-%m-%d %H:%M UTC} · "
            f"{version.n_rows:,} rows x {version.n_columns} columns"
            + (f" · {version.message}" if version.message else "")
        )
        if action.button("Restore", key=f"restore-{version.version_id}"):
            try:
                state.set_cleaned(versions.load(version.version_id), report=None)
            except VersioningError as exc:
                st.error(str(exc))
            else:
                st.rerun()
