"""Minimal client for OpenAI-compatible chat-completion APIs.

The default endpoint is the Hugging Face Inference Providers router, but any
service exposing ``POST {base_url}/chat/completions`` works (OpenAI, Groq,
Together, a local Ollama or vLLM server, ...).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from data_analyst_agent.config import Settings
from data_analyst_agent.exceptions import LLMAuthenticationError, LLMError

logger = logging.getLogger(__name__)


class ChatClient(Protocol):
    """Anything that can turn a system + user prompt into a text completion."""

    model: str

    def complete(
        self, system: str, user: str, *, max_tokens: int = 512, temperature: float = 0.2
    ) -> str: ...


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._timeout = timeout_seconds
        self._session = session or _session_with_retries()
        if api_key:
            self._session.headers.update({"Authorization": f"Bearer {api_key}"})

    def complete(
        self, system: str, user: str, *, max_tokens: int = 512, temperature: float = 0.2
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            response = self._session.post(self._url, json=payload, timeout=self._timeout)
        except requests.RequestException as exc:
            raise LLMError(f"Could not reach the LLM provider: {exc}") from exc

        if response.status_code in (401, 403):
            raise LLMAuthenticationError("The LLM provider rejected the API key.")
        if not response.ok:
            raise LLMError(
                f"LLM provider returned HTTP {response.status_code}: {response.text[:200]}"
            )

        content = _extract_content(response)
        logger.debug("LLM completion (%s): %d chars", self.model, len(content))
        return content


def build_client(settings: Settings) -> ChatClient | None:
    """Return a client if an LLM is configured, otherwise ``None``."""
    if not settings.llm_enabled:
        return None
    return OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def _extract_content(response: requests.Response) -> str:
    try:
        body: Any = response.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError("Unexpected response format from the LLM provider.") from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMError("The LLM provider returned an empty response.")
    return content.strip()


def _session_with_retries() -> requests.Session:
    retry = Retry(
        total=2,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"POST"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session
