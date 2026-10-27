from __future__ import annotations

import pandas as pd
import streamlit as st

from data_analyst_agent.assistant import Assistant, Source
from data_analyst_agent.config import Settings
from data_analyst_agent.exceptions import DataAgentError
from data_analyst_agent.schema import Schema
from data_analyst_agent.storage import TABLE_NAME
from data_analyst_agent.ui.components import query_result, require_data
from data_analyst_agent.ui.state import Answer, SessionState

_SQL_EDITOR_KEY = "sql_editor"


def render(state: SessionState, settings: Settings, assistant: Assistant) -> None:
    st.header("Ask & query")
    df = require_data(state.active)
    if df is None:
        return

    try:
        store = state.query_store(settings)
    except DataAgentError as exc:
        st.error(str(exc))
        return

    schema = Schema.from_frame(df)
    with st.expander(f'Table "{TABLE_NAME}": {len(df):,} rows, {df.shape[1]} columns'):
        st.dataframe(
            pd.DataFrame(
                {"Column": c.name, "Type": c.kind.value, "pandas dtype": c.dtype}
                for c in schema.columns
            ),
            hide_index=True,
            width="stretch",
        )

    st.subheader("Ask a question")
    if assistant.uses_llm and settings.llm_is_local:
        st.caption(
            f"Questions are translated to SQL by **{assistant.model}** running "
            "locally; no data leaves this machine."
        )
    elif assistant.uses_llm:
        st.caption(
            f"Questions are translated to SQL by **{assistant.model}**. Only column "
            "names and types are sent to generate SQL; up to 50 result rows are "
            "sent to write the summary."
        )
    else:
        st.caption(
            "No LLM configured: questions are answered with keyword rules "
            "(averages, totals, min/max, counts, grouped by a column)."
        )

    with st.form("ask"):
        question = st.text_input(
            "Question",
            placeholder="e.g. total revenue by region",
            label_visibility="collapsed",
        )
        asked = st.form_submit_button("Ask", type="primary")

    if asked and question.strip():
        with st.spinner("Thinking..."):
            try:
                generated = assistant.generate_sql(question, schema)
                result = store.query(generated.sql)
                insight = assistant.summarise(question, generated.sql, result.frame)
            except DataAgentError as exc:
                st.error(str(exc))
            else:
                state.answer = Answer(question, generated, result, insight)
                # Pre-fill the SQL editor so the query can be refined by hand.
                st.session_state[_SQL_EDITOR_KEY] = generated.sql

    if state.answer is not None:
        _render_answer(state.answer)

    st.divider()
    st.subheader("Run SQL")
    st.caption(f'Read-only SQLite. Query the table "{TABLE_NAME}".')
    sql = st.text_area(
        "SQL",
        key=_SQL_EDITOR_KEY,
        height=140,
        label_visibility="collapsed",
        placeholder=f'SELECT * FROM "{TABLE_NAME}" LIMIT 10',  # noqa: S608 (hint text only)
    )
    if st.button("Run SQL") and sql.strip():
        try:
            state.sql_result = store.query(sql)
        except DataAgentError as exc:
            st.error(str(exc))
    if state.sql_result is not None:
        query_result(state.sql_result, key="download-sql")


def _render_answer(answer: Answer) -> None:
    label = "AI-generated SQL" if answer.generated.source is Source.LLM else "Rule-based SQL"
    st.markdown(f"**{label}**")
    st.code(answer.generated.sql, language="sql", wrap_lines=True)
    for note in (answer.generated.note, answer.insight.note):
        if note:
            st.warning(note)
    st.markdown("**Answer**")
    st.markdown(answer.insight.text)
    query_result(answer.result, key="download-answer")
