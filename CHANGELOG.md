# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-27

A rewrite focused on correctness, safety and maintainability.

### Added
- Installable `data_analyst_agent` package (`src/` layout) with a framework-free core and a thin Streamlit UI.
- Read-only query sandbox with a row cap and query timeout.
- SSRF protection for the HTTP API loader (`ALLOW_PRIVATE_URLS` to opt out).
- Any OpenAI-compatible LLM provider via `LLM_BASE_URL` / `LLM_MODEL`; the UI reports when and why the rule-based fallback was used.
- Bundled messy sample dataset and the Palmer Penguins demo dataset.
- Checksummed Parquet snapshots that preserve column types.
- 186 tests, including end-to-end UI tests; strict mypy; ruff; CI on Python 3.11/3.12 with a Docker build and health check.
- ADRs, `.env.example`, `uv.lock`, reproducible README screenshots.

### Changed
- LLM calls use Hugging Face's Inference Providers router; the legacy `api-inference` endpoint no longer serves the old model.
- Profiling uses `fg-data-profiling`, the maintained successor of the deprecated `ydata-profiling`.
- Cleaning steps run in a fixed, documented order, and a column is only re-typed when every value converts.
- Docker image is a multi-stage, non-root build; `docker compose up` works without a `.env` file.

### Fixed
- Natural-language queries targeted a table name that never existed, so they always failed.
- Chart suggestions always fell through to a broken default because column types were read incorrectly.
- Whitespace cleaning turned missing values into the string `"nan"`.
- Outlier removal silently dropped every row with a missing numeric value.
- "Load version" buttons never worked (they were nested inside another button's handler).
- Keyword matching treated "by" inside words such as "maybe" as a grouping request.
- The sidebar showed stale dataset information until the next interaction.
- The Docker health check used `curl`, which is not installed in the image.

### Removed
- Unused modules and dead code, scikit-learn (imported but never used), and the placeholder test.

## [0.1.0] - 2025

Initial version.
