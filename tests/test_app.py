"""End-to-end tests that drive the real Streamlit app headlessly."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


def click(app: AppTest, label: str) -> AppTest:
    return next(b for b in app.button if b.label == label).click().run()


@pytest.fixture
def app(monkeypatch, tmp_path):
    for name in ("LLM_API_KEY", "HF_TOKEN", "HF_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
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


class FakeLLMServer(ThreadingHTTPServer):
    """An OpenAI-compatible endpoint that replays canned replies in order."""

    def __init__(self, replies: list[str]) -> None:
        super().__init__(("127.0.0.1", 0), _FakeLLMHandler)
        self.replies = replies
        self.prompts: list[str] = []

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/v1"


class _FakeLLMHandler(BaseHTTPRequestHandler):
    server: FakeLLMServer

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.prompts.append(body["messages"][-1]["content"])
        reply = json.dumps({"choices": [{"message": {"content": self.server.replies.pop(0)}}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(reply.encode())

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def fake_llm(monkeypatch):
    server = FakeLLMServer(
        [
            'SELECT "region", SUM(unit) FROM "dataset" GROUP BY "region"',
            'SELECT "region", SUM("units") AS "total_units" FROM "dataset" GROUP BY "region"',
            "North sold the most units.",
        ]
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LLM_BASE_URL", server.base_url)
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    yield server
    server.shutdown()
    server.server_close()


def test_ai_answer_self_corrects_a_failed_query(app, fake_llm):
    st.cache_resource.clear()  # pick up the fake LLM settings
    app.run()
    app.radio[0].set_value("Sample dataset").run()
    click(app, "Load sample dataset")

    next(t for t in app.text_input if t.label == "Question").input("total units by region")
    click(app, "Ask")

    assert not app.exception
    assert app.code[0].value.startswith('SELECT "region", SUM("units")')
    assert any("Self-corrected after 1 failed attempt" in e.label for e in app.expander)
    assert "no such column: unit" in fake_llm.prompts[1]
    assert any("North sold the most units." in md.value for md in app.markdown)


def test_rejects_write_queries(app):
    app.radio[0].set_value("Sample dataset").run()
    click(app, "Load sample dataset")

    editor = next(t for t in app.text_area if t.label == "SQL")
    editor.input('DROP TABLE "dataset"').run()
    click(app, "Run SQL")

    assert not app.exception
    assert any("Only SELECT" in e.value for e in app.error)
