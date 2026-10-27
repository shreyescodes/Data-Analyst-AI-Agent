"""Builders for fake HTTP responses used by ingestion and LLM tests."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import requests


def json_response(
    body: Any, status: int = 200, content_type: str = "application/json"
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    response.headers["Content-Type"] = content_type
    return response


def text_response(
    text: str, status: int = 200, content_type: str = "text/plain"
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = text.encode()
    response.headers["Content-Type"] = content_type
    return response


def mock_session(response: requests.Response) -> MagicMock:
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = response
    session.post.return_value = response
    return session
