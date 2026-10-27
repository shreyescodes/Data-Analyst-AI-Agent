import pytest
import requests

from data_analyst_agent.config import Settings
from data_analyst_agent.exceptions import LLMAuthenticationError, LLMError
from data_analyst_agent.llm import OpenAICompatibleClient, build_client
from tests.helpers import json_response, mock_session, text_response


def make_client(response: requests.Response):
    session = mock_session(response)
    client = OpenAICompatibleClient(
        base_url="https://llm.test/v1/", api_key="key", model="m", session=session
    )
    return client, session


def completion(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def test_sends_openai_compatible_request():
    client, session = make_client(json_response(completion(" hi ")))

    assert client.complete("sys", "user", max_tokens=5, temperature=0.0) == "hi"

    url = session.post.call_args.args[0]
    payload = session.post.call_args.kwargs["json"]
    assert url == "https://llm.test/v1/chat/completions"
    assert payload["model"] == "m"
    assert payload["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user"},
    ]
    assert payload["max_tokens"] == 5
    assert session.headers["Authorization"] == "Bearer key"


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors(status):
    client, _ = make_client(json_response({"error": "bad key"}, status=status))

    with pytest.raises(LLMAuthenticationError):
        client.complete("s", "u")


def test_http_errors():
    client, _ = make_client(text_response("overloaded", status=503))

    with pytest.raises(LLMError, match="503"):
        client.complete("s", "u")


@pytest.mark.parametrize(
    "body", [{}, {"choices": []}, completion(None), completion("   "), ["unexpected"]]
)
def test_malformed_responses(body):
    client, _ = make_client(json_response(body))

    with pytest.raises(LLMError):
        client.complete("s", "u")


def test_network_errors():
    client, session = make_client(json_response({}))
    session.post.side_effect = requests.Timeout("timed out")

    with pytest.raises(LLMError, match="timed out"):
        client.complete("s", "u")


def test_build_client_requires_key_or_custom_endpoint():
    assert build_client(Settings()) is None
    assert isinstance(build_client(Settings(llm_api_key="k")), OpenAICompatibleClient)
    local = Settings(llm_base_url="http://localhost:11434/v1", llm_model="qwen2.5-coder:3b")
    assert isinstance(build_client(local), OpenAICompatibleClient)


def test_no_authorization_header_without_key():
    session = mock_session(json_response(completion("ok")))

    OpenAICompatibleClient(
        base_url="http://localhost:11434/v1", api_key=None, model="m", session=session
    ).complete("s", "u")

    assert "Authorization" not in session.headers
