"""Typed wrapper around Streamlit's per-session state."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from data_analyst_agent.assistant import GeneratedSQL, Insight
from data_analyst_agent.charts import ChartSpec
from data_analyst_agent.cleaning import CleaningReport
from data_analyst_agent.config import Settings
from data_analyst_agent.storage import QueryResult, SQLiteStore

_STATE_KEY = "data_analyst_agent"


@dataclass(frozen=True, slots=True)
class Answer:
    question: str
    generated: GeneratedSQL
    result: QueryResult
    insight: Insight


@dataclass(slots=True)
class SessionState:
    raw: pd.DataFrame | None = None
    source_label: str | None = None
    source_id: str | None = None
    cleaned: pd.DataFrame | None = None
    cleaning_report: CleaningReport | None = None
    # Incremented whenever the active dataset changes; derived artefacts
    # (query store contents, profile report) record the revision they were
    # built from so they can be refreshed lazily.
    revision: int = 0

    answer: Answer | None = None
    sql_result: QueryResult | None = None
    chart: ChartSpec | None = None
    profile_html: str | None = None
    profile_revision: int = -1

    _store: SQLiteStore | None = field(default=None, repr=False)
    _store_revision: int = -1

    @property
    def active(self) -> pd.DataFrame | None:
        """The dataset every analysis tab works on: cleaned if available, else raw."""
        return self.cleaned if self.cleaned is not None else self.raw

    @property
    def is_cleaned(self) -> bool:
        return self.cleaned is not None

    def set_raw(self, df: pd.DataFrame, label: str, source_id: str | None = None) -> None:
        self.raw = df
        self.source_label = label
        self.source_id = source_id
        self.cleaned = None
        self.cleaning_report = None
        self._changed()

    def set_cleaned(self, df: pd.DataFrame, report: CleaningReport | None) -> None:
        self.cleaned = df
        self.cleaning_report = report
        self._changed()

    def query_store(self, settings: Settings) -> SQLiteStore:
        """Return the session's query store, reloading it if the data changed."""
        if self._store is None:
            self._store = SQLiteStore(
                row_limit=settings.query_row_limit,
                timeout_seconds=settings.query_timeout_seconds,
            )
        if self._store_revision != self.revision and self.active is not None:
            self._store.load(self.active)
            self._store_revision = self.revision
        return self._store

    def _changed(self) -> None:
        self.revision += 1
        self.answer = None
        self.sql_result = None
        self.chart = None
        self.profile_html = None


def get_state() -> SessionState:
    if _STATE_KEY not in st.session_state:
        st.session_state[_STATE_KEY] = SessionState()
    state: SessionState = st.session_state[_STATE_KEY]
    return state


def reset_state() -> None:
    state = st.session_state.pop(_STATE_KEY, None)
    if state is not None and state._store is not None:
        state._store.close()
