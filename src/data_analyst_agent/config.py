"""Application settings, read once from environment variables."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from data_analyst_agent.exceptions import ConfigurationError

DEFAULT_LLM_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_LLM_MODEL = "meta-llama/Llama-3.3-70B-Instruct"

# Checked in order; the first non-empty value wins. HF_* names are accepted so
# existing Hugging Face setups keep working without changes.
_API_KEY_VARS = ("LLM_API_KEY", "HF_TOKEN", "HF_API_KEY")


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration. See ``.env.example`` for every variable."""

    llm_api_key: str | None = None
    llm_base_url: str = DEFAULT_LLM_BASE_URL
    llm_model: str = DEFAULT_LLM_MODEL
    llm_timeout_seconds: float = 30.0
    max_upload_mb: int = 100
    query_row_limit: int = 10_000
    query_timeout_seconds: float = 10.0
    versions_dir: Path = Path("data_versions")
    allow_private_urls: bool = False
    log_level: str = "INFO"

    @property
    def llm_enabled(self) -> bool:
        """True with an API key, or when pointed at a custom endpoint.

        Local servers (Ollama, LM Studio, llama.cpp) need no key, so setting
        ``LLM_BASE_URL`` alone is enough to opt in.
        """
        return bool(self.llm_api_key) or self.llm_base_url != DEFAULT_LLM_BASE_URL

    @property
    def llm_is_local(self) -> bool:
        host = urlparse(self.llm_base_url).hostname or ""
        return host in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from ``env`` (defaults to ``os.environ``)."""
        env = os.environ if env is None else env

        api_key = next((env[name] for name in _API_KEY_VARS if env.get(name)), None)

        return cls(
            llm_api_key=api_key,
            llm_base_url=env.get("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).rstrip("/"),
            llm_model=env.get("LLM_MODEL", DEFAULT_LLM_MODEL),
            llm_timeout_seconds=_positive_float(env, "LLM_TIMEOUT_SECONDS", 30.0),
            max_upload_mb=_positive_int(env, "MAX_UPLOAD_MB", 100),
            query_row_limit=_positive_int(env, "QUERY_ROW_LIMIT", 10_000),
            query_timeout_seconds=_positive_float(env, "QUERY_TIMEOUT_SECONDS", 10.0),
            versions_dir=Path(env.get("DATA_VERSIONS_DIR", "data_versions")),
            allow_private_urls=_flag(env, "ALLOW_PRIVATE_URLS"),
            log_level=env.get("LOG_LEVEL", "INFO").upper(),
        )


def configure_logging(level: str) -> None:
    """Configure root logging once; later calls are no-ops."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


def _flag(env: Mapping[str, str], name: str) -> bool:
    raw = env.get(name, "").strip().lower()
    if raw in ("", "0", "false", "no"):
        return False
    if raw in ("1", "true", "yes"):
        return True
    raise ConfigurationError(f"{name} must be true or false, got {raw!r}")


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be positive, got {value}")
    return value


def _positive_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be positive, got {value}")
    return value
