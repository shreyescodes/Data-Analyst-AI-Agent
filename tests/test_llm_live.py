"""Tests against a real LLM endpoint (for example a local Ollama or llama.cpp server).

Skipped unless RUN_LIVE_LLM_TESTS=1 and an LLM is configured via LLM_* variables:

    RUN_LIVE_LLM_TESTS=1 LLM_BASE_URL=http://localhost:11434/v1 \
        LLM_MODEL=qwen2.5-coder:3b uv run pytest -m live
"""

import os

import pytest

from data_analyst_agent.assistant import Assistant, Source
from data_analyst_agent.config import Settings
from data_analyst_agent.llm import build_client
from data_analyst_agent.schema import Schema
from data_analyst_agent.storage import SQLiteStore

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_LLM_TESTS") != "1", reason="set RUN_LIVE_LLM_TESTS=1"
    ),
]


@pytest.fixture(scope="module")
def assistant():
    settings = Settings.from_env()
    if not settings.llm_enabled:
        pytest.skip("no LLM configured")
    return Assistant(build_client(settings))


def rows(frame):
    def canon(value):
        return round(float(value), 1) if isinstance(value, int | float) else value

    return {frozenset(canon(v) for v in row) for row in frame.itertuples(index=False)}


def test_connection(assistant):
    assistant.check_connection()


def test_generated_sql_answers_the_question(assistant, sales):
    with SQLiteStore() as store:
        store.load(sales)
        generated, result = assistant.answer(
            "What is the total units sold per region?", Schema.from_frame(sales), store.query
        )

    assert generated.source is Source.LLM, generated.note
    assert rows(result.frame) == {
        frozenset({"North", 17.0}),
        frozenset({"South", 8.0}),
        frozenset({"East", 1.0}),
    }


def test_summary_mentions_the_result(assistant, sales):
    result = sales.groupby("region", as_index=False)["units"].sum()

    insight = assistant.summarise("Which region sold the most units?", "SELECT ...", result)

    assert insight.source is Source.LLM, insight.note
    assert "North" in insight.text
