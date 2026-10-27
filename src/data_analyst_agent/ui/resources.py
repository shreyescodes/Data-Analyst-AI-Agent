"""Process-wide objects, created once and shared across Streamlit sessions."""

from __future__ import annotations

import streamlit as st

from data_analyst_agent.assistant import Assistant
from data_analyst_agent.config import Settings, configure_logging
from data_analyst_agent.llm import build_client
from data_analyst_agent.versioning import VersionStore


@st.cache_resource
def get_settings() -> Settings:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    return settings


@st.cache_resource
def get_assistant() -> Assistant:
    return Assistant(build_client(get_settings()))


@st.cache_resource
def get_version_store() -> VersionStore:
    return VersionStore(get_settings().versions_dir)
