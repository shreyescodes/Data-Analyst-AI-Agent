from __future__ import annotations

import contextlib
import json
import tempfile
from importlib import resources
from pathlib import Path

import pandas as pd
import streamlit as st

from data_analyst_agent import ingestion
from data_analyst_agent.config import Settings
from data_analyst_agent.exceptions import DataAgentError, IngestionError
from data_analyst_agent.ui.components import dataset_overview
from data_analyst_agent.ui.state import SessionState

_SAMPLE_FILE = "sample_sales.csv"
_MB = 1024 * 1024


def render(state: SessionState, settings: Settings) -> None:
    st.header("Load data")
    source = st.radio(
        "Source",
        ["Upload a file", "Sample dataset", "HTTP API", "SQL database"],
        horizontal=True,
        label_visibility="collapsed",
    )

    try:
        if source == "Upload a file":
            _from_upload(state, settings)
        elif source == "Sample dataset":
            _from_sample(state)
        elif source == "HTTP API":
            _from_api(state, settings)
        else:
            _from_database(state)
    except DataAgentError as exc:
        st.error(str(exc))

    if state.raw is not None:
        st.divider()
        st.subheader(f"Loaded: {state.source_label}")
        dataset_overview(state.raw)


def _from_upload(state: SessionState, settings: Settings) -> None:
    uploaded = st.file_uploader(
        "CSV or Excel file",
        type=list(ingestion.SUPPORTED_FILE_TYPES),
        help=f"Up to {settings.max_upload_mb} MB.",
    )
    # The uploader returns the same file on every rerun; only load it once.
    if uploaded is None or uploaded.file_id == state.source_id:
        return
    if uploaded.size > settings.max_upload_mb * _MB:
        raise IngestionError(f"File exceeds the {settings.max_upload_mb} MB limit.")
    with st.spinner("Reading file..."):
        df = ingestion.load_file(uploaded, uploaded.name)
    state.set_raw(df, uploaded.name, source_id=uploaded.file_id)


def _from_sample(state: SessionState) -> None:
    st.write(
        "A small, deliberately messy sales dataset with stray whitespace, "
        "duplicates, missing values and numbers stored as text."
    )
    if st.button("Load sample dataset", type="primary"):
        sample = resources.files("data_analyst_agent") / "data" / _SAMPLE_FILE
        with sample.open("rb") as fh:
            state.set_raw(ingestion.load_file(fh, _SAMPLE_FILE), _SAMPLE_FILE)


def _from_api(state: SessionState, settings: Settings) -> None:
    with st.form("api_source"):
        url = st.text_input("Endpoint URL", placeholder="https://api.example.com/records")
        token = st.text_input("Bearer token (optional)", type="password")
        raw_headers = st.text_area(
            "Extra headers as JSON (optional)", placeholder='{"X-Api-Version": "2"}'
        )
        submitted = st.form_submit_button("Fetch", type="primary")
    if not submitted:
        return

    headers = _parse_headers(raw_headers)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with st.spinner("Fetching..."):
        df = ingestion.load_from_api(
            url.strip(), headers=headers, allow_private=settings.allow_private_urls
        )
    state.set_raw(df, url.strip())


def _from_database(state: SessionState) -> None:
    mode = st.radio("Connection", ["Upload SQLite file", "Connection URL"], horizontal=True)
    with st.form("db_source"):
        if mode == "Upload SQLite file":
            db_file = st.file_uploader("SQLite database", type=["db", "sqlite", "sqlite3"])
            url = None
        else:
            db_file = None
            url = st.text_input(
                "SQLAlchemy URL",
                type="password",
                placeholder="postgresql+psycopg://user:pass@host:5432/db",
                help="PostgreSQL and MySQL need the optional drivers: "
                'pip install ".[postgres]" or ".[mysql]".',
            )
        table = st.text_input("Table name")
        submitted = st.form_submit_button("Load table", type="primary")
    if not submitted:
        return

    if db_file is not None:
        df = _load_uploaded_sqlite(db_file.getvalue(), table)
        label = f"{db_file.name}:{table}"
    elif url:
        df = ingestion.load_from_database(url, table)
        label = f"database:{table}"
    else:
        raise IngestionError("Provide a database file or connection URL.")
    state.set_raw(df, label)


def _load_uploaded_sqlite(content: bytes, table: str) -> pd.DataFrame:
    # SQLite needs a real file path, so write the upload to a temp file.
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(content)
        path = Path(tmp.name)
    try:
        return ingestion.load_from_database(f"sqlite:///{path.as_posix()}", table)
    finally:
        with contextlib.suppress(OSError):
            path.unlink()


def _parse_headers(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IngestionError(f"Headers are not valid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise IngestionError("Headers must be a JSON object.")
    return {str(k): str(v) for k, v in parsed.items()}
