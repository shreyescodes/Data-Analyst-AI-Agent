from pathlib import Path

import pytest

from data_analyst_agent.config import DEFAULT_LLM_BASE_URL, Settings
from data_analyst_agent.exceptions import ConfigurationError


def test_defaults_when_environment_is_empty():
    settings = Settings.from_env({})

    assert settings.llm_api_key is None
    assert not settings.llm_enabled
    assert settings.llm_base_url == DEFAULT_LLM_BASE_URL
    assert settings.versions_dir == Path("data_versions")


def test_reads_all_variables():
    settings = Settings.from_env(
        {
            "LLM_API_KEY": "secret",
            "LLM_BASE_URL": "http://localhost:11434/v1/",
            "LLM_MODEL": "llama3",
            "QUERY_ROW_LIMIT": "50",
            "QUERY_TIMEOUT_SECONDS": "2.5",
            "DATA_VERSIONS_DIR": "/data/versions",
            "LOG_LEVEL": "debug",
        }
    )

    assert settings.llm_enabled
    assert settings.llm_base_url == "http://localhost:11434/v1"  # trailing slash stripped
    assert settings.llm_model == "llama3"
    assert settings.query_row_limit == 50
    assert settings.query_timeout_seconds == 2.5
    assert settings.versions_dir == Path("/data/versions")
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize(
    ("env", "enabled", "local"),
    [
        ({}, False, False),
        ({"LLM_API_KEY": "k"}, True, False),
        ({"LLM_BASE_URL": "http://localhost:11434/v1"}, True, True),
        ({"LLM_BASE_URL": "http://host.docker.internal:1234/v1"}, True, True),
        ({"LLM_BASE_URL": "https://api.openai.com/v1"}, True, False),
        ({"LLM_BASE_URL": "https://router.huggingface.co/v1/"}, False, False),
    ],
)
def test_llm_enabled_by_key_or_custom_endpoint(env, enabled, local):
    settings = Settings.from_env(env)

    assert settings.llm_enabled is enabled
    assert settings.llm_is_local is local


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"HF_API_KEY": "legacy"}, "legacy"),
        ({"HF_TOKEN": "hf", "HF_API_KEY": "legacy"}, "hf"),
        ({"LLM_API_KEY": "primary", "HF_TOKEN": "hf"}, "primary"),
        ({"LLM_API_KEY": "", "HF_TOKEN": "hf"}, "hf"),
    ],
)
def test_api_key_precedence(env, expected):
    assert Settings.from_env(env).llm_api_key == expected


@pytest.mark.parametrize(
    ("raw", "expected"), [("true", True), ("YES", True), ("0", False), ("", False)]
)
def test_boolean_flags(raw, expected):
    assert Settings.from_env({"ALLOW_PRIVATE_URLS": raw}).allow_private_urls is expected


def test_rejects_invalid_flags():
    with pytest.raises(ConfigurationError, match="ALLOW_PRIVATE_URLS"):
        Settings.from_env({"ALLOW_PRIVATE_URLS": "maybe"})


@pytest.mark.parametrize("value", ["abc", "0", "-5"])
def test_rejects_invalid_integers(value):
    with pytest.raises(ConfigurationError, match="QUERY_ROW_LIMIT"):
        Settings.from_env({"QUERY_ROW_LIMIT": value})
