# Contributing

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/shreyescodes/Data-Analyst-AI-Agent.git
cd Data-Analyst-AI-Agent
make install        # uv sync --locked + pre-commit hooks
make run            # http://localhost:8501
```

Without `make`, run the commands from the [Makefile](Makefile) directly
(for example `uv run pytest`).

## Before opening a pull request

```bash
make check          # ruff lint + format check, mypy --strict, pytest with coverage
```

CI runs the same checks on Python 3.11 and 3.12 and builds the Docker image.

## Conventions

- **Layering:** business logic lives in the core modules of
  `src/data_analyst_agent/` and must not import Streamlit. `ui/` only
  translates between widgets and core calls. See
  [ADR-0003](docs/decisions/0003-framework-free-core-with-thin-streamlit-ui.md).
- **Errors:** raise a subclass of `DataAgentError` for expected failures (bad
  input, provider errors); the UI shows its message. Let genuine bugs raise.
- **Tests:** every behaviour change needs a test; every bug fix needs a
  regression test that fails without the fix. UI flows can be tested with
  `streamlit.testing.v1.AppTest` (see `tests/test_app.py`).
- **Dependencies:** add them to `pyproject.toml` and run `uv lock`. Prefer the
  standard library or an existing dependency.
- **Decisions:** record significant design decisions as ADRs in
  `docs/decisions/`.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- **Changelog:** add user-facing changes to `CHANGELOG.md` under "Unreleased".

## Screenshots

If you change the UI, regenerate the README images (requires Google Chrome):

```bash
make screenshots
```
