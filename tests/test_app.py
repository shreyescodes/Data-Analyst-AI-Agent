"""End-to-end tests that drive the real Streamlit app headlessly."""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


def click(app: AppTest, label: str) -> AppTest:
    return next(b for b in app.button if b.label == label).click().run()


@pytest.fixture
def app(monkeypatch, tmp_path):
    for name in ("LLM_API_KEY", "HF_TOKEN", "HF_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_VERSIONS_DIR", str(tmp_path / "versions"))
    st.cache_resource.clear()  # settings are cached per process

    app = AppTest.from_file(APP_PATH, default_timeout=60)
    app.run()
    return app


def test_starts_without_data(app):
    assert not app.exception
    assert app.title[0].value == "Data Analyst AI Agent"
    assert any("Load a dataset" in info.value for info in app.info)


def test_load_clean_query_and_snapshot(app):
    app.radio[0].set_value("Sample dataset").run()
    click(app, "Load sample dataset")
    assert not app.exception
    assert any("248 rows" in md.value for md in app.sidebar.markdown)

    click(app, "Run cleaning")
    assert not app.exception
    assert any("222 rows" in md.value for md in app.sidebar.markdown)

    question = next(t for t in app.text_input if t.label == "Question")
    question.input("total units by region")
    click(app, "Ask")
    assert not app.exception
    assert app.code[0].value.startswith('SELECT "region", SUM("units")')

    click(app, "Save snapshot")
    assert not app.exception
    assert any("Saved snapshot" in s.value for s in app.success)


def test_rejects_write_queries(app):
    app.radio[0].set_value("Sample dataset").run()
    click(app, "Load sample dataset")

    editor = next(t for t in app.text_area if t.label == "SQL")
    editor.input('DROP TABLE "dataset"').run()
    click(app, "Run SQL")

    assert not app.exception
    assert any("Only SELECT" in e.value for e in app.error)
