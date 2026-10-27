from __future__ import annotations

import pandas as pd
import streamlit as st

from data_analyst_agent import __version__
from data_analyst_agent.assistant import Assistant
from data_analyst_agent.config import Settings
from data_analyst_agent.exceptions import LLMError


def render(settings: Settings, assistant: Assistant) -> None:
    st.header("Settings")
    st.caption(
        "Configuration is read from environment variables at startup. "
        "See `.env.example` for the full list."
    )

    st.dataframe(
        pd.DataFrame(
            [
                ("LLM endpoint", settings.llm_base_url),
                ("LLM model", settings.llm_model),
                ("LLM API key", "configured" if settings.llm_enabled else "not set"),
                ("Query row limit", f"{settings.query_row_limit:,}"),
                ("Query timeout", f"{settings.query_timeout_seconds:g} s"),
                ("Max upload size", f"{settings.max_upload_mb} MB"),
                ("Snapshot directory", str(settings.versions_dir)),
                (
                    "Private-network API URLs",
                    "allowed" if settings.allow_private_urls else "blocked",
                ),
                ("App version", __version__),
            ],
            columns=["Setting", "Value"],
        ),
        hide_index=True,
        width="stretch",
    )

    if not settings.llm_enabled:
        st.info(
            "Set `LLM_API_KEY` (or `HF_TOKEN`) to enable AI-generated SQL and "
            "summaries. A free Hugging Face token works with the default endpoint: "
            "https://huggingface.co/settings/tokens"
        )
        return

    if st.button("Test LLM connection"):
        with st.spinner("Contacting provider..."):
            try:
                assistant.check_connection()
            except LLMError as exc:
                st.error(str(exc))
            else:
                st.success(f"Connected to {settings.llm_model}.")
